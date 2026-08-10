from __future__ import annotations

import json
import hashlib
import logging
import secrets
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.ai import ARTIST_MODELS, get_ai_provider
from app.config import (
    GLOBAL_DAILY_ROUND_LIMIT,
    GLOBAL_GENERATING_ROUND_LIMIT,
    INVITE_ATTEMPT_LIMIT,
    INVITE_ATTEMPT_WINDOW_SECONDS,
    INVITE_RATE_LIMIT_MAX_SOURCES,
    PER_USER_DAILY_ROUND_LIMIT,
    WEBSOCKET_TICKET_TTL_SECONDS,
)
from app.db import SessionLocal
from app.models import (
    Game,
    GameCreate,
    GameEvent,
    GameRoundCreate,
    GameStats,
    GameInvite,
    GameInvitePreview,
    InviteCreate,
    InviteJoin,
    InviteStatus,
    DeviceToken,
    DeviceTokenRegister,
    GeneratedSvg,
    GuessResult,
    Round,
    RoundCreate,
    RoundStatus,
    SvgStatus,
    TestNotificationResponse,
    User,
    UserCreate,
    UserSession,
    UserUpdate,
    WebSocketTicket,
)
from app.notifications import get_notification_provider, notify_user
from app.orm_models import DeviceToken as DeviceTokenORM
from app.orm_models import Game as GameORM
from app.orm_models import GameEvent as GameEventORM
from app.orm_models import GameInvite as GameInviteORM
from app.orm_models import GeneratedSvg as GeneratedSvgORM
from app.orm_models import Guess as GuessORM
from app.orm_models import NotificationAttempt as NotificationAttemptORM
from app.orm_models import Round as RoundORM
from app.orm_models import User as UserORM
from app.orm_models import WebSocketTicket as WebSocketTicketORM
from app.safety import validate_challenge_prompt


logger = logging.getLogger("ai_pictionary.services")
PUBLIC_GENERATION_ERROR_CODE = "generation_failed"
PUBLIC_GENERATION_ERROR_MESSAGE = "Drawing generation failed. Please try again."
AUTHENTICATION_ERROR = "Invalid or missing bearer token"
INVITE_RATE_LIMIT_ERROR = {"code": "invite_rate_limited", "message": "Too many invite attempts"}

_invite_attempts: dict[str, deque[float]] = defaultdict(deque)
_invite_attempts_lock = Lock()


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


def hash_access_token(access_token: str) -> str:
    return hashlib.sha256(access_token.encode("utf-8")).hexdigest()


def issue_websocket_ticket(db: Session, game_id: str, user_id: str) -> WebSocketTicket:
    game = db.get(GameORM, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    require_game_participant(game, user_id)
    raw_ticket = secrets.token_urlsafe(32)
    expires_at = now() + timedelta(seconds=WEBSOCKET_TICKET_TTL_SECONDS)
    db.add(
        WebSocketTicketORM(
            id=new_id(),
            ticket_hash=hash_access_token(raw_ticket),
            user_id=user_id,
            game_id=game_id,
            expires_at=expires_at,
        )
    )
    db.commit()
    return WebSocketTicket(ticket=raw_ticket, expires_at=serialize_dt(expires_at) or "")


def consume_websocket_ticket(db: Session, raw_ticket: str, game_id: str) -> str:
    consumed_at = now()
    ticket_hash = hash_access_token(raw_ticket)
    ticket = db.scalar(
        select(WebSocketTicketORM).where(
            WebSocketTicketORM.ticket_hash == ticket_hash,
            WebSocketTicketORM.game_id == game_id,
        )
    )
    if not ticket:
        raise HTTPException(status_code=401, detail=AUTHENTICATION_ERROR)
    transition = db.execute(
        update(WebSocketTicketORM)
        .where(
            WebSocketTicketORM.id == ticket.id,
            WebSocketTicketORM.consumed_at.is_(None),
            WebSocketTicketORM.expires_at >= consumed_at,
        )
        .values(consumed_at=consumed_at)
        .execution_options(synchronize_session=False)
    )
    if transition.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=401, detail=AUTHENTICATION_ERROR)
    game = db.get(GameORM, game_id)
    if not game:
        db.rollback()
        raise HTTPException(status_code=401, detail=AUTHENTICATION_ERROR)
    try:
        require_game_participant(game, ticket.user_id)
    except HTTPException as exc:
        db.rollback()
        raise HTTPException(status_code=401, detail=AUTHENTICATION_ERROR) from exc
    db.commit()
    return ticket.user_id


def authenticate_access_token(db: Session, access_token: str) -> UserORM:
    token_hash = hash_access_token(access_token)
    user = db.scalar(select(UserORM).where(UserORM.session_token_hash == token_hash))
    if not user:
        raise HTTPException(
            status_code=401,
            detail=AUTHENTICATION_ERROR,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def assert_actor_matches(asserted_user_id: Optional[str], actor_user_id: str) -> None:
    if asserted_user_id is not None and asserted_user_id != actor_user_id:
        raise HTTPException(status_code=403, detail="Authenticated user does not match requested actor")


def check_invite_attempt(source: str, timestamp: Optional[float] = None) -> None:
    current = time.monotonic() if timestamp is None else timestamp
    cutoff = current - INVITE_ATTEMPT_WINDOW_SECONDS
    with _invite_attempts_lock:
        if source not in _invite_attempts and len(_invite_attempts) >= INVITE_RATE_LIMIT_MAX_SOURCES:
            stale_sources = [
                tracked_source
                for tracked_source, tracked_attempts in _invite_attempts.items()
                if not tracked_attempts or tracked_attempts[-1] <= cutoff
            ]
            for tracked_source in stale_sources:
                del _invite_attempts[tracked_source]
            if len(_invite_attempts) >= INVITE_RATE_LIMIT_MAX_SOURCES:
                raise HTTPException(status_code=429, detail=INVITE_RATE_LIMIT_ERROR)
        attempts = _invite_attempts[source]
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if len(attempts) >= INVITE_ATTEMPT_LIMIT:
            raise HTTPException(status_code=429, detail=INVITE_RATE_LIMIT_ERROR)
        attempts.append(current)


def reset_invite_attempt_limiter() -> None:
    with _invite_attempts_lock:
        _invite_attempts.clear()


def serialize_dt(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def ensure_user(db: Session, user_id: str, display_name: Optional[str] = None) -> UserORM:
    user = db.get(UserORM, user_id)
    if user:
        return user
    user = UserORM(id=user_id, display_name=display_name or user_id)
    db.add(user)
    db.flush()
    return user


def create_user(db: Session, payload: UserCreate) -> User:
    user = UserORM(
        id=new_id(),
        display_name=payload.display_name.strip(),
        avatar_url=payload.avatar_url,
        avatar_emoji=payload.avatar_emoji,
        avatar_color=payload.avatar_color,
        auth_provider=None,
        auth_subject=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return to_user_schema(user)


def create_user_session(db: Session, payload: UserCreate) -> UserSession:
    access_token = secrets.token_urlsafe(32)
    user = UserORM(
        id=new_id(),
        display_name=payload.display_name.strip(),
        avatar_url=payload.avatar_url,
        avatar_emoji=payload.avatar_emoji,
        avatar_color=payload.avatar_color,
        auth_provider=None,
        auth_subject=None,
        session_token_hash=hash_access_token(access_token),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserSession(user=to_user_schema(user), access_token=access_token)


def get_user(db: Session, user_id: str) -> User:
    user = db.get(UserORM, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return to_user_schema(user)


def update_user(db: Session, user_id: str, payload: UserUpdate) -> User:
    user = db.get(UserORM, user_id)
    if not user:
        raise HTTPException(status_code=404, detail={"code": "user_not_found", "message": "User not found"})
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()
    if payload.avatar_emoji is not None:
        user.avatar_emoji = payload.avatar_emoji
    if payload.avatar_color is not None:
        user.avatar_color = payload.avatar_color
    user.updated_at = now()
    db.commit()
    db.refresh(user)
    return to_user_schema(user)


def create_game(db: Session, payload: GameCreate) -> Game:
    if payload.player_1_id == payload.player_2_id:
        raise HTTPException(status_code=400, detail="A game needs two different users")
    require_user(db, payload.player_1_id)
    require_user(db, payload.player_2_id)
    game = GameORM(
        id=new_id(),
        player_1_id=payload.player_1_id,
        player_2_id=payload.player_2_id,
        current_turn_user_id=payload.player_1_id,
    )
    db.add(game)
    db.flush()
    add_event(db, game.id, "game.created", {"player_1_id": game.player_1_id, "player_2_id": game.player_2_id})
    db.commit()
    db.refresh(game)
    return to_game_schema(db, game)


def list_games_for_user(db: Session, user_id: str) -> list[Game]:
    require_user(db, user_id)
    games = (
        db.execute(
            select(GameORM)
            .where(or_(GameORM.player_1_id == user_id, GameORM.player_2_id == user_id))
            .order_by(GameORM.updated_at.desc())
        )
        .scalars()
        .all()
    )
    return [to_game_schema(db, game, viewer_user_id=user_id) for game in games]


def get_game(db: Session, game_id: str, user_id: Optional[str] = None) -> Game:
    game = db.get(GameORM, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if user_id:
        require_game_participant(game, user_id)
    return to_game_schema(db, game, viewer_user_id=user_id)


def get_game_stats(db: Session, game_id: str, user_id: str) -> GameStats:
    game = db.get(GameORM, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    require_game_participant(game, user_id)
    guesses = (
        db.execute(
            select(GuessORM)
            .join(RoundORM, GuessORM.round_id == RoundORM.id)
            .where(RoundORM.game_id == game_id)
            .order_by(GuessORM.created_at.asc())
        )
        .scalars()
        .all()
    )
    totals = {game.player_1_id: 0, game.player_2_id: 0}
    counts = {game.player_1_id: 0, game.player_2_id: 0}
    best_score: Optional[int] = None
    for guess in guesses:
        totals[guess.user_id] = totals.get(guess.user_id, 0) + guess.score
        counts[guess.user_id] = counts.get(guess.user_id, 0) + 1
        best_score = guess.score if best_score is None else max(best_score, guess.score)
    averages = {
        player_id: round(totals[player_id] / counts[player_id], 1) if counts[player_id] else 0.0
        for player_id in totals
    }
    return GameStats(
        game_id=game.id,
        rounds_played=len(guesses),
        total_score_by_user=totals,
        average_score_by_user=averages,
        best_score=best_score,
        current_turn_user_id=game.current_turn_user_id,
        last_activity_at=serialize_dt(game.updated_at) or "",
    )


def create_legacy_round(db: Session, payload: RoundCreate) -> Round:
    ensure_user(db, payload.creator_user_id)
    ensure_user(db, payload.guesser_user_id)
    game = find_or_create_game(db, payload.creator_user_id, payload.guesser_user_id)
    game.current_turn_user_id = payload.creator_user_id
    return create_round_for_game(
        db,
        game.id,
        GameRoundCreate(prompt=payload.prompt, creator_user_id=payload.creator_user_id),
        enforce_turn=False,
        commit=True,
    )


def acquire_generation_admission(db: Session) -> None:
    db.execute(
        text(
            "INSERT INTO generation_admission_gate (id, version) VALUES (1, 0) "
            "ON CONFLICT(id) DO NOTHING"
        )
    )
    db.execute(
        text("UPDATE generation_admission_gate SET version = version + 1 WHERE id = 1")
    )


def enforce_new_round_budgets(db: Session, creator_user_id: str) -> None:
    acquire_generation_admission(db)
    current = now()
    day_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    user_daily_count = db.scalar(
        select(func.count(RoundORM.id)).where(
            RoundORM.creator_user_id == creator_user_id,
            RoundORM.created_at >= day_start,
        )
    ) or 0
    if user_daily_count >= PER_USER_DAILY_ROUND_LIMIT:
        raise HTTPException(
            status_code=429,
            detail={"code": "user_daily_round_limit", "message": "Daily round limit reached"},
        )

    global_daily_count = db.scalar(
        select(func.count(RoundORM.id)).where(RoundORM.created_at >= day_start)
    ) or 0
    if global_daily_count >= GLOBAL_DAILY_ROUND_LIMIT:
        raise HTTPException(
            status_code=429,
            detail={"code": "global_daily_round_limit", "message": "Global daily round limit reached"},
        )
    enforce_generation_capacity(db)


def enforce_generation_capacity(db: Session, *, admission_acquired: bool = True) -> None:
    if not admission_acquired:
        acquire_generation_admission(db)
    generating_count = db.scalar(
        select(func.count(RoundORM.id)).where(RoundORM.status == RoundStatus.generating.value)
    ) or 0
    if generating_count >= GLOBAL_GENERATING_ROUND_LIMIT:
        raise HTTPException(
            status_code=503,
            detail={"code": "generation_capacity_reached", "message": "Generation capacity reached"},
        )


def create_round_for_game(
    db: Session,
    game_id: str,
    payload: GameRoundCreate,
    enforce_turn: bool = True,
    commit: bool = True,
) -> Round:
    creator_user_id = payload.creator_user_id
    if not creator_user_id:
        raise HTTPException(status_code=422, detail="Creator user is required")
    game = db.get(GameORM, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if creator_user_id not in {game.player_1_id, game.player_2_id}:
        raise HTTPException(status_code=403, detail="Creator is not a player in this game")
    if enforce_turn and game.current_turn_user_id != creator_user_id:
        raise HTTPException(status_code=409, detail="It is not this user's turn")

    guesser_user_id = other_player_id(game, creator_user_id)
    active_round = latest_round_orm(db, game.id)
    if active_round and active_round.status in {RoundStatus.generating.value, RoundStatus.ready_to_guess.value}:
        raise HTTPException(status_code=409, detail="This game already has an active round")
    enforce_new_round_budgets(db, creator_user_id)

    round_record = RoundORM(
        id=new_id(),
        game_id=game.id,
        creator_user_id=creator_user_id,
        guesser_user_id=guesser_user_id,
        original_prompt=validate_challenge_prompt(payload.prompt),
        status=RoundStatus.generating.value,
    )
    db.add(round_record)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This game already has an active round") from exc
    logger.info(
        "round.created",
        extra={
            "round_id": round_record.id,
            "game_id": game.id,
            "creator_user_id": creator_user_id,
        },
    )

    for index, model in enumerate(ARTIST_MODELS):
        db.add(
            GeneratedSvgORM(
                id=new_id(),
                round_id=round_record.id,
                sort_order=index,
                model_name=str(model["model"]),
                model_tier=str(model["tier"]),
                status=SvgStatus.pending.value,
            )
        )
    add_event(db, game.id, "round.created", {"round_id": round_record.id}, user_id=creator_user_id)
    notify_user(
        db,
        guesser_user_id,
        "New AI drawing challenge",
        "Your opponent created a prompt. The artists are drawing.",
        {"game_id": game.id, "round_id": round_record.id, "type": "round.created"},
    )
    if commit:
        db.commit()
    return get_round(db, round_record.id, reveal_prompt=True)


async def generate_round_svgs(round_id: str) -> None:
    with SessionLocal() as db:
        round_record = load_round_orm(db, round_id)
        logger.info(
            "generation.round_started",
            extra={
                "round_id": round_id,
                "game_id": round_record.game_id,
                "creator_user_id": round_record.creator_user_id,
            },
        )
        add_event(db, round_record.game_id, "round.generation_started", {"round_id": round_id})
        db.commit()

        try:
            provider = get_ai_provider()
        except Exception as exc:
            logger.warning(
                "generation.provider_initialization_failed",
                extra={
                    "round_id": round_id,
                    "game_id": round_record.game_id,
                    "exception_type": qualified_exception_type(exc),
                },
            )
            finalize_provider_initialization_failure(db, round_record)
            db.commit()
            return

        provider_name = getattr(provider, "name", provider.__class__.__name__)
        for svg in round_record.generated_svgs:
            if svg.status == SvgStatus.done.value:
                continue
            svg.provider_used = provider_name
            svg.status = SvgStatus.generating.value
            svg.attempts += 1
            db.commit()
            started = time.perf_counter()
            try:
                model_config = next(model for model in ARTIST_MODELS if model["tier"] == svg.model_tier)
                logger.info(
                    "generation.svg_started",
                    extra={
                        "round_id": round_id,
                        "game_id": round_record.game_id,
                        "svg_id": svg.id,
                        "provider": provider_name,
                        "model": model_config["model"],
                        "tier": model_config["tier"],
                    },
                )
                svg.svg_text = await provider.generate_svg(round_record.original_prompt, model_config)
                svg.status = SvgStatus.done.value
                svg.error_message = None
                svg.generation_time_seconds = round(time.perf_counter() - started, 2)
                logger.info(
                    "generation.svg_completed",
                    extra={
                        "round_id": round_id,
                        "game_id": round_record.game_id,
                        "svg_id": svg.id,
                        "tier": svg.model_tier,
                        "sanitized_svg_size": len((svg.svg_text or "").encode("utf-8")),
                        "generation_time_seconds": svg.generation_time_seconds,
                    },
                )
                add_event(
                    db,
                    round_record.game_id,
                    "svg.generated",
                    {"round_id": round_id, "svg_id": svg.id, "tier": svg.model_tier},
                )
            except Exception as exc:
                svg.status = SvgStatus.failed.value
                svg.error_message = PUBLIC_GENERATION_ERROR_MESSAGE
                svg.generation_time_seconds = round(time.perf_counter() - started, 2)
                logger.warning(
                    "generation.svg_failed",
                    extra={
                        "round_id": round_id,
                        "game_id": round_record.game_id,
                        "svg_id": svg.id,
                        "tier": svg.model_tier,
                        "provider": provider_name,
                        "exception_type": qualified_exception_type(exc),
                    },
                )
                add_event(
                    db,
                    round_record.game_id,
                    "svg.failed",
                    {
                        "round_id": round_id,
                        "svg_id": svg.id,
                        "tier": svg.model_tier,
                        "code": PUBLIC_GENERATION_ERROR_CODE,
                        "message": PUBLIC_GENERATION_ERROR_MESSAGE,
                    },
                )
            db.commit()

        db.refresh(round_record)
        done_count = sum(1 for svg in round_record.generated_svgs if svg.status == SvgStatus.done.value)
        round_record.status = RoundStatus.ready_to_guess.value if done_count else RoundStatus.failed.value
        add_event(
            db,
            round_record.game_id,
            "round.ready_to_guess" if done_count else "round.failed",
            {
                "round_id": round_id,
                "available_svgs": done_count,
                **(
                    {
                        "code": PUBLIC_GENERATION_ERROR_CODE,
                        "message": PUBLIC_GENERATION_ERROR_MESSAGE,
                    }
                    if not done_count
                    else {}
                ),
            },
        )
        if done_count:
            notify_user(
                db,
                round_record.guesser_user_id,
                "Sketches are ready",
                "Your AI drawing challenge is ready to guess.",
                {"game_id": round_record.game_id, "round_id": round_id, "type": "round.ready_to_guess"},
            )
        db.commit()


def qualified_exception_type(exc: Exception) -> str:
    return f"{exc.__class__.__module__}.{exc.__class__.__name__}"


def finalize_provider_initialization_failure(db: Session, round_record: RoundORM) -> None:
    for svg in round_record.generated_svgs:
        if svg.status not in {SvgStatus.pending.value, SvgStatus.generating.value}:
            continue
        if svg.status == SvgStatus.pending.value:
            svg.attempts += 1
        svg.status = SvgStatus.failed.value
        svg.provider_used = None
        svg.error_message = PUBLIC_GENERATION_ERROR_MESSAGE
        add_event(
            db,
            round_record.game_id,
            "svg.failed",
            {
                "round_id": round_record.id,
                "svg_id": svg.id,
                "tier": svg.model_tier,
                "code": PUBLIC_GENERATION_ERROR_CODE,
                "message": PUBLIC_GENERATION_ERROR_MESSAGE,
            },
        )
    done_count = sum(1 for svg in round_record.generated_svgs if svg.status == SvgStatus.done.value)
    round_record.status = RoundStatus.ready_to_guess.value if done_count else RoundStatus.failed.value
    add_event(
        db,
        round_record.game_id,
        "round.ready_to_guess" if done_count else "round.failed",
        {
            "round_id": round_record.id,
            "available_svgs": done_count,
            "code": PUBLIC_GENERATION_ERROR_CODE,
            "message": PUBLIC_GENERATION_ERROR_MESSAGE,
        },
    )


def prepare_generation_retry(db: Session, round_id: str, user_id: str) -> Round:
    round_record = load_round_orm(db, round_id)
    game = db.get(GameORM, round_record.game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    require_game_participant(game, user_id)
    if round_record.creator_user_id != user_id:
        raise HTTPException(status_code=403, detail="Only the prompt creator can retry generation")
    if game.current_turn_user_id != user_id:
        raise HTTPException(status_code=409, detail="It is not this user's turn")
    if round_record.status == RoundStatus.guessed.value:
        raise HTTPException(status_code=409, detail="Cannot retry a round after it has been guessed")
    if round_record.status == RoundStatus.generating.value:
        raise HTTPException(status_code=409, detail="Round generation is already in progress")

    retryable = [svg for svg in round_record.generated_svgs if svg.status != SvgStatus.done.value]
    if not retryable:
        raise HTTPException(status_code=409, detail="All artist sketches are already ready")

    enforce_generation_capacity(db, admission_acquired=False)
    updated_at = now()
    transition = db.execute(
        update(RoundORM)
        .where(RoundORM.id == round_id, RoundORM.status == round_record.status)
        .values(status=RoundStatus.generating.value, updated_at=updated_at)
    )
    if transition.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Round state changed; refresh and try again")
    round_record.status = RoundStatus.generating.value
    round_record.updated_at = updated_at
    logger.info(
        "generation.retry_requested",
        extra={"round_id": round_id, "game_id": round_record.game_id, "user_id": user_id},
    )
    for svg in retryable:
        svg.status = SvgStatus.pending.value
        svg.provider_used = None
        svg.error_message = None
        svg.updated_at = now()
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This game already has an active round") from exc
    add_event(
        db,
        round_record.game_id,
        "round.generation_retry_requested",
        {"round_id": round_id, "retryable_svgs": len(retryable)},
        user_id=user_id,
    )
    db.commit()
    db.refresh(round_record)
    return to_round_schema(round_record, reveal_prompt=should_reveal_prompt(round_record, user_id))


def get_round(db: Session, round_id: str, reveal_prompt: bool = True) -> Round:
    round_record = load_round_orm(db, round_id)
    return to_round_schema(round_record, reveal_prompt=reveal_prompt)


def get_round_for_user(db: Session, round_id: str, user_id: str) -> Round:
    round_record = load_round_orm(db, round_id)
    game = db.get(GameORM, round_record.game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    require_game_participant(game, user_id)
    reveal_prompt = should_reveal_prompt(round_record, user_id)
    return to_round_schema(round_record, reveal_prompt=reveal_prompt)


def submit_guess(db: Session, round_id: str, guess_text: str, user_id: Optional[str] = None, clue_count_used: int = 1) -> GuessResult:
    round_record = load_round_orm(db, round_id)
    if round_record.status != RoundStatus.ready_to_guess.value:
        raise HTTPException(status_code=409, detail="Round is not ready for guesses yet")
    if round_record.guesses:
        raise HTTPException(status_code=409, detail="This round has already been guessed")

    guesser_user_id = user_id or round_record.guesser_user_id
    if guesser_user_id != round_record.guesser_user_id:
        raise HTTPException(status_code=403, detail="Only the guesser can submit a guess")
    if guesser_user_id == round_record.creator_user_id:
        raise HTTPException(status_code=403, detail="You cannot guess your own prompt")

    completed_at = now()
    transition = db.execute(
        update(RoundORM)
        .where(RoundORM.id == round_id, RoundORM.status == RoundStatus.ready_to_guess.value)
        .values(status=RoundStatus.guessed.value, completed_at=completed_at, updated_at=completed_at)
    )
    if transition.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="This round has already been guessed")

    provider = get_ai_provider()
    judge = provider.score_guess_sync(round_record.original_prompt, guess_text)
    penalty = max(0, clue_count_used - 1) * 8
    score = max(0, int(judge["score"]) - penalty)
    judge["score"] = score

    guess = GuessORM(
        id=new_id(),
        round_id=round_record.id,
        user_id=guesser_user_id,
        guess_text=guess_text.strip(),
        score=score,
        judge_result_json=json.dumps(judge),
        component_scores_json=json.dumps(judge.get("component_scores", {})),
        clue_count_used=clue_count_used,
    )
    round_record.status = RoundStatus.guessed.value
    round_record.completed_at = completed_at
    game = db.get(GameORM, round_record.game_id)
    if game:
        game.current_turn_user_id = guesser_user_id
        game.updated_at = now()
    db.add(guess)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This round has already been guessed") from exc
    add_event(db, round_record.game_id, "guess.submitted", {"round_id": round_record.id}, user_id=guesser_user_id)
    add_event(db, round_record.game_id, "round.scored", {"round_id": round_record.id, "score": score})
    add_event(db, round_record.game_id, "turn.changed", {"current_turn_user_id": guesser_user_id})
    notify_user(
        db,
        round_record.creator_user_id,
        "Your prompt was guessed",
        f"Score: {score}. It is your opponent's turn now.",
        {"game_id": round_record.game_id, "round_id": round_record.id, "type": "guess.submitted"},
    )
    notify_user(
        db,
        guesser_user_id,
        "Your turn",
        "Create the next weird prompt.",
        {"game_id": round_record.game_id, "type": "turn.changed"},
    )
    db.commit()
    db.refresh(guess)
    return guess_to_schema(guess)


def list_events(
    db: Session,
    game_id: str,
    after_id: int = 0,
    user_id: Optional[str] = None,
) -> list[GameEvent]:
    game = db.get(GameORM, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if user_id is not None:
        require_game_participant(game, user_id)
    events = (
        db.execute(
            select(GameEventORM)
            .where(GameEventORM.game_id == game_id, GameEventORM.id > after_id)
            .order_by(GameEventORM.id.asc())
        )
        .scalars()
        .all()
    )
    return [to_event_schema(event) for event in events]


def list_all_events(db: Session, limit: int = 100) -> list[GameEvent]:
    events = db.execute(select(GameEventORM).order_by(GameEventORM.id.desc()).limit(limit)).scalars().all()
    return [to_event_schema(event) for event in reversed(events)]


def list_events_for_user(db: Session, user_id: str, limit: int = 100) -> list[GameEvent]:
    events = (
        db.execute(
            select(GameEventORM)
            .join(GameORM, GameORM.id == GameEventORM.game_id)
            .where(or_(GameORM.player_1_id == user_id, GameORM.player_2_id == user_id))
            .order_by(GameEventORM.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [to_event_schema(event) for event in reversed(events)]


def list_all_games(db: Session, limit: int = 100) -> list[Game]:
    games = db.execute(select(GameORM).order_by(GameORM.updated_at.desc()).limit(limit)).scalars().all()
    return [to_game_schema(db, game) for game in games]


def list_notification_attempts(db: Session, limit: int = 100) -> list[dict[str, Any]]:
    attempts = db.execute(select(NotificationAttemptORM).order_by(NotificationAttemptORM.created_at.desc()).limit(limit)).scalars().all()
    return [
        {
            "id": attempt.id,
            "user_id": attempt.user_id,
            "device_token_id": attempt.device_token_id,
            "provider": attempt.provider,
            "title": attempt.title,
            "status": attempt.status,
            "response": json.loads(attempt.response_json or "{}"),
            "error_message": attempt.error_message,
            "created_at": serialize_dt(attempt.created_at),
        }
        for attempt in attempts
    ]


def list_notification_attempts_for_user(db: Session, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
    attempts = (
        db.execute(
            select(NotificationAttemptORM)
            .where(NotificationAttemptORM.user_id == user_id)
            .order_by(NotificationAttemptORM.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": attempt.id,
            "user_id": attempt.user_id,
            "device_token_id": attempt.device_token_id,
            "provider": attempt.provider,
            "title": attempt.title,
            "status": attempt.status,
            "response": json.loads(attempt.response_json or "{}"),
            "error_message": attempt.error_message,
            "created_at": serialize_dt(attempt.created_at),
        }
        for attempt in attempts
    ]


def create_invite(db: Session, payload: InviteCreate) -> GameInvite:
    creator_user_id = payload.creator_user_id
    if not creator_user_id:
        raise HTTPException(status_code=422, detail="Creator user is required")
    require_user(db, creator_user_id)
    code = generate_invite_code(db)
    invite = GameInviteORM(
        code=code,
        creator_user_id=creator_user_id,
        status=InviteStatus.pending.value,
        expires_at=now() + timedelta(hours=payload.expires_in_hours),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return to_invite_schema(invite)


def get_invite(db: Session, code: str) -> GameInvite:
    invite = load_invite(db, code)
    refresh_invite_expiry(db, invite)
    return to_invite_schema(invite)


def get_invite_preview(db: Session, code: str) -> GameInvitePreview:
    invite = load_invite(db, code)
    refresh_invite_expiry(db, invite)
    return to_invite_preview_schema(invite)


def join_invite(db: Session, code: str, payload: InviteJoin) -> Game:
    joiner_user_id = payload.user_id
    if not joiner_user_id:
        raise HTTPException(status_code=422, detail="Joining user is required")
    invite = load_invite(db, code)
    refresh_invite_expiry(db, invite)
    if invite.status != InviteStatus.pending.value:
        logger.info("invite.join_rejected", extra={"user_id": joiner_user_id, "status": invite.status})
        raise HTTPException(status_code=409, detail="Invite is not pending")
    if invite.creator_user_id == joiner_user_id:
        logger.info("invite.self_join_rejected", extra={"user_id": joiner_user_id})
        raise HTTPException(status_code=403, detail="Creator cannot join their own invite")
    require_user(db, joiner_user_id)

    game = GameORM(
        id=new_id(),
        player_1_id=invite.creator_user_id,
        player_2_id=joiner_user_id,
        current_turn_user_id=invite.creator_user_id,
    )
    db.add(game)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Invite could not be joined") from exc
    accepted_at = now()
    transition = db.execute(
        update(GameInviteORM)
        .where(
            GameInviteORM.code == code,
            GameInviteORM.status == InviteStatus.pending.value,
            GameInviteORM.expires_at >= accepted_at,
        )
        .values(
            status=InviteStatus.accepted.value,
            accepted_by_user_id=joiner_user_id,
            accepted_at=accepted_at,
            game_id=game.id,
            updated_at=accepted_at,
        )
        .execution_options(synchronize_session=False)
    )
    if transition.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Invite is not pending")
    add_event(db, game.id, "game.created", {"player_1_id": game.player_1_id, "player_2_id": game.player_2_id})
    add_event(db, game.id, "invite.accepted", {}, user_id=joiner_user_id)
    notify_user(
        db,
        invite.creator_user_id,
        "Invite accepted",
        "Your opponent joined. It is your turn to create a prompt.",
        {"game_id": game.id, "type": "invite.accepted"},
    )
    db.commit()
    db.refresh(game)
    return to_game_schema(db, game, viewer_user_id=joiner_user_id)


def register_device_token(db: Session, payload: DeviceTokenRegister) -> DeviceToken:
    user_id = payload.user_id
    if not user_id:
        raise HTTPException(status_code=422, detail="User is required")
    require_user(db, user_id)
    existing = (
        db.execute(
            select(DeviceTokenORM).where(
                DeviceTokenORM.user_id == user_id,
                DeviceTokenORM.provider == payload.provider,
                DeviceTokenORM.token == payload.token,
            )
        )
        .scalars()
        .first()
    )
    token = existing or DeviceTokenORM(id=new_id(), user_id=user_id, provider=payload.provider, token=payload.token)
    token.platform = payload.platform
    token.status = "active"
    token.updated_at = now()
    db.add(token)
    db.commit()
    db.refresh(token)
    logger.info("device_token.registered", extra={"user_id": user_id, "provider": payload.provider, "platform": payload.platform})
    return to_device_token_schema(token)


def send_debug_test_notification(db: Session, user_id: str, game_id: Optional[str] = None) -> TestNotificationResponse:
    require_user(db, user_id)
    active_tokens = (
        db.execute(select(DeviceTokenORM).where(DeviceTokenORM.user_id == user_id, DeviceTokenORM.status == "active"))
        .scalars()
        .all()
    )
    data: dict[str, Any] = {"type": "debug.test", "source": "beta_debug"}
    if game_id:
        game = db.get(GameORM, game_id)
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        require_game_participant(game, user_id)
        data["game_id"] = game_id
    notify_user(db, user_id, "AI Pictionary test", "Push notifications are connected.", data)
    db.commit()
    return TestNotificationResponse(
        user_id=user_id,
        queued=True,
        active_device_tokens=len(active_tokens),
        provider=get_notification_provider().name,
    )


def find_or_create_game(db: Session, player_1_id: str, player_2_id: str) -> GameORM:
    game = (
        db.execute(
            select(GameORM).where(
                or_(
                    (GameORM.player_1_id == player_1_id) & (GameORM.player_2_id == player_2_id),
                    (GameORM.player_1_id == player_2_id) & (GameORM.player_2_id == player_1_id),
                )
            )
        )
        .scalars()
        .first()
    )
    if game:
        return game
    game = GameORM(
        id=new_id(),
        player_1_id=player_1_id,
        player_2_id=player_2_id,
        current_turn_user_id=player_1_id,
    )
    db.add(game)
    db.flush()
    add_event(db, game.id, "game.created", {"player_1_id": player_1_id, "player_2_id": player_2_id})
    return game


def require_user(db: Session, user_id: str) -> UserORM:
    user = db.get(UserORM, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def require_game_participant(game: GameORM, user_id: str) -> None:
    if user_id not in {game.player_1_id, game.player_2_id}:
        raise HTTPException(status_code=403, detail="User is not a participant in this game")


def other_player_id(game: GameORM, user_id: str) -> str:
    if user_id == game.player_1_id:
        return game.player_2_id
    if user_id == game.player_2_id:
        return game.player_1_id
    raise HTTPException(status_code=403, detail="User is not in this game")


def load_round_orm(db: Session, round_id: str) -> RoundORM:
    round_record = (
        db.execute(
            select(RoundORM)
            .where(RoundORM.id == round_id)
            .options(selectinload(RoundORM.generated_svgs), selectinload(RoundORM.guesses))
        )
        .scalars()
        .first()
    )
    if not round_record:
        raise HTTPException(status_code=404, detail="Round not found")
    return round_record


def load_invite(db: Session, code: str) -> GameInviteORM:
    invite = db.get(GameInviteORM, code)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    return invite


def refresh_invite_expiry(db: Session, invite: GameInviteORM) -> None:
    expires_at = invite.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if invite.status == InviteStatus.pending.value and expires_at < now():
        invite.status = InviteStatus.expired.value
        db.commit()
        db.refresh(invite)


def generate_invite_code(db: Session) -> str:
    for _ in range(20):
        code = secrets.token_urlsafe(16)
        if not db.get(GameInviteORM, code):
            return code
    raise HTTPException(status_code=503, detail="Could not create an invite")


def latest_round_orm(db: Session, game_id: str) -> Optional[RoundORM]:
    return (
        db.execute(
            select(RoundORM)
            .where(RoundORM.game_id == game_id)
            .order_by(RoundORM.created_at.desc(), RoundORM.id.desc())
            .options(selectinload(RoundORM.generated_svgs), selectinload(RoundORM.guesses))
        )
        .scalars()
        .first()
    )


def add_event(db: Session, game_id: str, event_type: str, payload: dict[str, Any], user_id: Optional[str] = None) -> None:
    db.add(GameEventORM(game_id=game_id, user_id=user_id, event_type=event_type, payload_json=json.dumps(payload)))


def to_user_schema(user: UserORM) -> User:
    return User(
        id=user.id,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        avatar_emoji=getattr(user, "avatar_emoji", "🙂"),
        avatar_color=getattr(user, "avatar_color", "#F5C84C"),
        auth_provider=user.auth_provider,
        auth_subject=user.auth_subject,
        created_at=serialize_dt(user.created_at) or "",
        updated_at=serialize_dt(user.updated_at) or "",
    )


def to_game_schema(db: Session, game: GameORM, viewer_user_id: Optional[str] = None) -> Game:
    latest = latest_round_orm(db, game.id)
    if latest:
        logger.info(
            "game.latest_round_selected",
            extra={
                "requested_game_id": game.id,
                "selected_round_id": latest.id,
                "selected_round_game_id": latest.game_id,
                "selected_round_created_at": str(latest.created_at),
            }
        )
        if latest.game_id != game.id:
            logger.error("SERIOUS BUG: latest_round_orm returned a round from a different game", extra={"requested_game_id": game.id, "selected_round_id": latest.id, "selected_round_game_id": latest.game_id})
    opponent = None
    if viewer_user_id in {game.player_1_id, game.player_2_id}:
        opponent_id = other_player_id(game, viewer_user_id)
        opponent_user = db.get(UserORM, opponent_id)
        opponent = to_user_schema(opponent_user) if opponent_user else None
    return Game(
        id=game.id,
        player_1_id=game.player_1_id,
        player_2_id=game.player_2_id,
        current_turn_user_id=game.current_turn_user_id,
        status=game.status,
        created_at=serialize_dt(game.created_at) or "",
        updated_at=serialize_dt(game.updated_at) or "",
        latest_round=to_round_schema(latest, reveal_prompt=should_reveal_prompt(latest, viewer_user_id)) if latest else None,
        opponent=opponent,
    )


def should_reveal_prompt(round_record: Optional[RoundORM], viewer_user_id: Optional[str]) -> bool:
    if not round_record:
        return True
    if round_record.status == RoundStatus.guessed.value:
        return True
    if not viewer_user_id:
        return False
    return viewer_user_id == round_record.creator_user_id


def to_round_schema(round_record: RoundORM, reveal_prompt: bool = True) -> Round:
    latest_guess = sorted(round_record.guesses, key=lambda item: item.created_at, reverse=True)[0] if round_record.guesses else None
    return Round(
        id=round_record.id,
        game_id=round_record.game_id,
        creator_user_id=round_record.creator_user_id,
        guesser_user_id=round_record.guesser_user_id,
        original_prompt=round_record.original_prompt if reveal_prompt else "",
        status=round_record.status,
        generated_svgs=[to_svg_schema(svg) for svg in round_record.generated_svgs],
        created_at=serialize_dt(round_record.created_at) or "",
        updated_at=serialize_dt(round_record.updated_at) or "",
        completed_at=serialize_dt(round_record.completed_at),
        clue_reveal_count=round_record.clue_reveal_count,
        guess=guess_to_schema(latest_guess) if latest_guess else None,
    )


def to_svg_schema(svg: GeneratedSvgORM) -> GeneratedSvg:
    return GeneratedSvg(
        id=svg.id,
        model_name=svg.model_name,
        model_tier=svg.model_tier,
        provider_used=svg.provider_used,
        status=svg.status,
        svg_text=svg.svg_text,
        error_message=svg.error_message,
        attempts=svg.attempts,
        generation_time_seconds=svg.generation_time_seconds,
    )


def guess_to_schema(guess: GuessORM) -> GuessResult:
    judge = json.loads(guess.judge_result_json)
    return GuessResult(
        round_id=guess.round_id,
        guess_text=guess.guess_text,
        score=guess.score,
        matched_parts=list(judge.get("matched_parts", [])),
        missed_parts=list(judge.get("missed_parts", [])),
        short_feedback=str(judge.get("short_feedback", "")),
        judge_result_json=judge,
        component_scores=json.loads(guess.component_scores_json or "{}"),
        clue_count_used=guess.clue_count_used,
        clue_penalty=max(0, guess.clue_count_used - 1) * 8,
        created_at=serialize_dt(guess.created_at) or "",
    )


def to_event_schema(event: GameEventORM) -> GameEvent:
    return GameEvent(
        id=event.id,
        game_id=event.game_id,
        user_id=event.user_id,
        event_type=event.event_type,
        payload=json.loads(event.payload_json or "{}"),
        created_at=serialize_dt(event.created_at) or "",
    )


def to_invite_schema(invite: GameInviteORM) -> GameInvite:
    return GameInvite(
        code=invite.code,
        creator_user_id=invite.creator_user_id,
        game_id=invite.game_id,
        status=invite.status,
        expires_at=serialize_dt(invite.expires_at) or "",
        accepted_by_user_id=invite.accepted_by_user_id,
        accepted_at=serialize_dt(invite.accepted_at),
        created_at=serialize_dt(invite.created_at) or "",
        updated_at=serialize_dt(invite.updated_at) or "",
    )


def to_invite_preview_schema(invite: GameInviteORM) -> GameInvitePreview:
    return GameInvitePreview(
        code=invite.code,
        creator_user_id=invite.creator_user_id,
        status=invite.status,
        expires_at=serialize_dt(invite.expires_at) or "",
    )


def to_device_token_schema(token: DeviceTokenORM) -> DeviceToken:
    return DeviceToken(
        id=token.id,
        user_id=token.user_id,
        provider=token.provider,
        token=token.token,
        platform=token.platform,
        status=token.status,
        created_at=serialize_dt(token.created_at) or "",
        updated_at=serialize_dt(token.updated_at) or "",
    )


def reset_local_database(db: Session) -> dict[str, int]:
    """
    Deletes all records from the local database in an order that respects foreign keys.
    Returns a dictionary of deleted row counts by table.
    """
    tables_to_delete = [
        ("websocket_tickets", WebSocketTicketORM),
        ("notification_attempts", NotificationAttemptORM),
        ("device_tokens", DeviceTokenORM),
        ("generated_svgs", GeneratedSvgORM),
        ("guesses", GuessORM),
        ("game_events", GameEventORM),
        ("rounds", RoundORM),
        ("game_invites", GameInviteORM),
        ("games", GameORM),
        ("users", UserORM),
    ]

    deleted_counts = {}
    for table_name, model in tables_to_delete:
        from sqlalchemy import delete
        result = db.execute(delete(model))
        deleted_counts[table_name] = result.rowcount

    db.commit()
    logger.info("database.reset_local_data", extra={"deleted": deleted_counts})
    return deleted_counts
