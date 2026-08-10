from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.ai import get_ai_status
from app.config import CORS_ALLOW_ORIGINS, DEBUG, ENV, is_local_env
from app.db import get_db, init_db
from app.models import (
    AIStatus,
    DeviceToken,
    DeviceTokenRegister,
    DeviceTokenUnregister,
    DeviceTokenUnregisterResponse,
    Game,
    GameCreate,
    GameEvent,
    GameInvite,
    GameInvitePreview,
    GameRoundCreate,
    GameStats,
    GuessCreate,
    GuessResult,
    InviteCreate,
    InviteCodeRequest,
    InviteJoin,
    InviteJoinRequest,
    LocalDataResetRequest,
    LocalDataResetResponse,
    RetryGenerationRequest,
    Round,
    RoundCreate,
    TestNotificationRequest,
    TestNotificationResponse,
    User,
    UserCreate,
    UserSession,
    UserUpdate,
    WebSocketTicket as WebSocketTicketSchema,
)
from app import services
from app.orm_models import User as UserORM

logger = logging.getLogger("ai_pictionary.api")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


def safe_request_path(path: str) -> str:
    if path.startswith("/invites/"):
        suffix = "/join" if path.endswith("/join") else ""
        return f"/invites/{{code}}{suffix}"
    return path


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="AI Pictionary MVP", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

bearer_scheme = HTTPBearer(auto_error=False)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.exception("request.failed", extra={"request_id": request_id, "path": safe_request_path(request.url.path)})
        return JSONResponse(
            status_code=500,
            content={"detail": {"code": "internal_error", "message": "Internal server error", "request_id": request_id}},
            headers={"x-request-id": request_id},
        )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["x-request-id"] = request_id
    logger.info(
        "request.completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": safe_request_path(request.url.path),
            "status_code": response.status_code,
            "elapsed_ms": elapsed_ms,
        },
    )
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def require_debug() -> None:
    require_local_debug()


def require_local_debug() -> None:
    if not is_local_env(ENV) or not DEBUG:
        raise HTTPException(status_code=404, detail="Not found")


def current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> UserORM:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail=services.AUTHENTICATION_ERROR,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return services.authenticate_access_token(db, credentials.credentials)


def require_owner(requested_user_id: str, actor: UserORM) -> None:
    if requested_user_id != actor.id:
        raise HTTPException(status_code=403, detail="User can only access their own profile")


def invite_attempt_source(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@app.get("/ai/status", response_model=AIStatus)
def ai_status() -> dict:
    return get_ai_status()


@app.get("/debug/health/full")
def debug_health_full(actor: UserORM = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    require_debug()
    return {"status": "ok", "env": ENV, "ai": get_ai_status(), "database": "ok"}


@app.get("/debug/events")
def debug_events(limit: int = 100, actor: UserORM = Depends(current_user), db: Session = Depends(get_db)) -> list[GameEvent]:
    require_debug()
    return services.list_events_for_user(db, actor.id, limit=limit)


@app.get("/debug/games")
def debug_games(limit: int = 100, actor: UserORM = Depends(current_user), db: Session = Depends(get_db)) -> list[Game]:
    require_debug()
    return services.list_games_for_user(db, actor.id)[:limit]


@app.get("/debug/notification-outbox")
def debug_notification_outbox(limit: int = 100, actor: UserORM = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    require_debug()
    from app.notifications import notification_outbox_snapshot

    return {
        "outbox": [
            message.__dict__
            for message in notification_outbox_snapshot()
            if message.user_id == actor.id
        ][-limit:],
        "attempts": services.list_notification_attempts_for_user(db, actor.id, limit=limit),
    }


@app.post("/debug/send-test-notification", response_model=TestNotificationResponse)
def debug_send_test_notification(payload: TestNotificationRequest, actor: UserORM = Depends(current_user), db: Session = Depends(get_db)) -> TestNotificationResponse:
    require_debug()
    services.assert_actor_matches(payload.user_id, actor.id)
    if payload.game_id:
        game = db.get(services.GameORM, payload.game_id)
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        services.require_game_participant(game, actor.id)
    return services.send_debug_test_notification(db, actor.id, game_id=payload.game_id)


@app.post(
    "/debug/reset-local-data",
    response_model=LocalDataResetResponse,
    dependencies=[Depends(require_local_debug)],
)
def debug_reset_local_data(
    payload: LocalDataResetRequest,
    actor: UserORM = Depends(current_user),
    db: Session = Depends(get_db),
) -> LocalDataResetResponse:
    return services.reset_local_data(db)


@app.post("/users", response_model=UserSession, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> UserSession:
    return services.create_user_session(db, payload)


@app.get("/users/{user_id}", response_model=User)
def get_user(
    user_id: str,
    actor: UserORM = Depends(current_user),
    db: Session = Depends(get_db),
) -> User:
    require_owner(user_id, actor)
    return services.get_user(db, user_id)


@app.patch("/users/{user_id}", response_model=User)
def update_user(
    user_id: str,
    payload: UserUpdate,
    actor: UserORM = Depends(current_user),
    db: Session = Depends(get_db),
) -> User:
    require_owner(user_id, actor)
    return services.update_user(db, user_id, payload)


@app.post(
    "/games",
    response_model=Game,
    status_code=201,
    dependencies=[Depends(require_local_debug)],
)
def create_game(
    payload: GameCreate,
    actor: UserORM = Depends(current_user),
    db: Session = Depends(get_db),
) -> Game:
    services.assert_actor_matches(payload.player_1_id, actor.id)
    return services.create_game(db, payload)


@app.get("/users/{user_id}/games", response_model=list[Game])
def list_games(
    user_id: str,
    actor: UserORM = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[Game]:
    require_owner(user_id, actor)
    return services.list_games_for_user(db, user_id)


@app.get("/games/{game_id}", response_model=Game)
def get_game(
    game_id: str,
    actor: UserORM = Depends(current_user),
    db: Session = Depends(get_db),
) -> Game:
    return services.get_game(db, game_id, user_id=actor.id)


@app.get("/games/{game_id}/stats", response_model=GameStats)
def get_game_stats(
    game_id: str,
    actor: UserORM = Depends(current_user),
    db: Session = Depends(get_db),
) -> GameStats:
    return services.get_game_stats(db, game_id, user_id=actor.id)


@app.get("/games/{game_id}/events", response_model=list[GameEvent])
def get_game_events(
    game_id: str,
    after_id: int = 0,
    actor: UserORM = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[GameEvent]:
    return services.list_events(db, game_id, after_id=after_id, user_id=actor.id)


@app.post("/invites", response_model=GameInvite, status_code=201)
def create_invite(
    payload: InviteCreate,
    actor: UserORM = Depends(current_user),
    db: Session = Depends(get_db),
) -> GameInvite:
    services.assert_actor_matches(payload.creator_user_id, actor.id)
    return services.create_invite(db, payload.model_copy(update={"creator_user_id": actor.id}))


@app.post("/invites/preview", response_model=GameInvitePreview)
def preview_invite(payload: InviteCodeRequest, request: Request, db: Session = Depends(get_db)) -> GameInvitePreview:
    services.check_invite_attempt(invite_attempt_source(request))
    return services.get_invite_preview(db, payload.code)


@app.post("/invites/join", response_model=Game, status_code=201)
def join_invite(
    payload: InviteJoinRequest,
    request: Request,
    actor: UserORM = Depends(current_user),
    db: Session = Depends(get_db),
) -> Game:
    services.check_invite_attempt(invite_attempt_source(request))
    services.assert_actor_matches(payload.user_id, actor.id)
    return services.join_invite(db, payload.code, InviteJoin(user_id=actor.id))


@app.get("/invites/{code}", response_model=GameInvitePreview, dependencies=[Depends(require_local_debug)])
def get_invite_legacy(code: str, request: Request, actor: UserORM = Depends(current_user), db: Session = Depends(get_db)) -> GameInvitePreview:
    services.check_invite_attempt(invite_attempt_source(request))
    return services.get_invite_preview(db, code)


@app.post("/invites/{code}/join", response_model=Game, status_code=201, dependencies=[Depends(require_local_debug)])
def join_invite_legacy(code: str, payload: InviteJoin, request: Request, actor: UserORM = Depends(current_user), db: Session = Depends(get_db)) -> Game:
    services.check_invite_attempt(invite_attempt_source(request))
    services.assert_actor_matches(payload.user_id, actor.id)
    return services.join_invite(db, code, InviteJoin(user_id=actor.id))


@app.post("/games/{game_id}/websocket-ticket", response_model=WebSocketTicketSchema, status_code=201)
def create_websocket_ticket(game_id: str, actor: UserORM = Depends(current_user), db: Session = Depends(get_db)) -> WebSocketTicketSchema:
    return services.issue_websocket_ticket(db, game_id, actor.id)


@app.post("/device-tokens", response_model=DeviceToken, status_code=201)
def register_device_token(
    payload: DeviceTokenRegister,
    actor: UserORM = Depends(current_user),
    db: Session = Depends(get_db),
) -> DeviceToken:
    services.assert_actor_matches(payload.user_id, actor.id)
    return services.register_device_token(db, payload.model_copy(update={"user_id": actor.id}))


@app.post("/device-tokens/unregister", response_model=DeviceTokenUnregisterResponse)
def unregister_device_token(
    payload: DeviceTokenUnregister,
    actor: UserORM = Depends(current_user),
    db: Session = Depends(get_db),
) -> DeviceTokenUnregisterResponse:
    return services.unregister_device_token(
        db,
        actor.id,
        payload.provider,
        payload.token,
        payload.registration_id,
    )


@app.post("/games/{game_id}/rounds", response_model=Round, status_code=201)
async def create_game_round(
    game_id: str,
    payload: GameRoundCreate,
    background_tasks: BackgroundTasks,
    actor: UserORM = Depends(current_user),
    db: Session = Depends(get_db),
) -> Round:
    services.assert_actor_matches(payload.creator_user_id, actor.id)
    round_record = services.create_round_for_game(
        db,
        game_id,
        payload.model_copy(update={"creator_user_id": actor.id}),
    )
    background_tasks.add_task(services.generate_round_svgs, round_record.id)
    return round_record


@app.post(
    "/rounds",
    response_model=Round,
    status_code=201,
    dependencies=[Depends(require_local_debug)],
)
async def create_round_endpoint(
    payload: RoundCreate,
    background_tasks: BackgroundTasks,
    actor: UserORM = Depends(current_user),
    db: Session = Depends(get_db),
) -> Round:
    services.assert_actor_matches(payload.creator_user_id, actor.id)
    round_record = services.create_legacy_round(db, payload)
    background_tasks.add_task(services.generate_round_svgs, round_record.id)
    return round_record


@app.get("/rounds/{round_id}", response_model=Round)
def get_round(
    round_id: str,
    actor: UserORM = Depends(current_user),
    db: Session = Depends(get_db),
) -> Round:
    return services.get_round_for_user(db, round_id, user_id=actor.id)


@app.post("/rounds/{round_id}/retry-generation", response_model=Round)
async def retry_round_generation(
    round_id: str,
    payload: RetryGenerationRequest,
    background_tasks: BackgroundTasks,
    actor: UserORM = Depends(current_user),
    db: Session = Depends(get_db),
) -> Round:
    services.assert_actor_matches(payload.user_id, actor.id)
    round_record = services.prepare_generation_retry(db, round_id, actor.id)
    background_tasks.add_task(services.generate_round_svgs, round_id)
    return round_record


@app.post("/rounds/{round_id}/guess", response_model=GuessResult)
async def guess_round(
    round_id: str,
    payload: GuessCreate,
    actor: UserORM = Depends(current_user),
    db: Session = Depends(get_db),
) -> GuessResult:
    services.assert_actor_matches(payload.user_id, actor.id)
    return services.submit_guess(
        db,
        round_id,
        payload.guess_text,
        user_id=actor.id,
        clue_count_used=payload.clue_count_used,
    )


@app.websocket("/ws/games/{game_id}")
async def game_events_websocket(websocket: WebSocket, game_id: str) -> None:
    ticket = websocket.query_params.get("ticket")
    if not ticket:
        await websocket.close(code=1008)
        return
    try:
        last_event_id = max(0, int(websocket.query_params.get("after_id", "0")))
    except ValueError:
        await websocket.close(code=1008)
        return
    try:
        with services.SessionLocal() as db:
            user_id = services.consume_websocket_ticket(db, ticket, game_id)
    except HTTPException:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    try:
        await websocket.send_json({"type": "connected", "game_id": game_id, "after_id": last_event_id})
        logger.info("websocket.connected", extra={"game_id": game_id, "user_id": user_id})
        while True:
            with services.SessionLocal() as db:
                events = services.list_events(db, game_id, after_id=last_event_id, user_id=user_id)
            for event in events:
                last_event_id = event.id
                await websocket.send_json({"type": "event", "event": event.model_dump()})
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=0.75)
            except asyncio.TimeoutError:
                continue
            if message["type"] == "websocket.disconnect":
                logger.info("websocket.disconnected", extra={"game_id": game_id, "user_id": user_id})
                return
    except WebSocketDisconnect:
        logger.info("websocket.disconnected", extra={"game_id": game_id, "user_id": user_id})
        return
    except HTTPException:
        await websocket.send_json({"type": "error", "message": "Not allowed"})
        await websocket.close(code=1008)
