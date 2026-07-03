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
from sqlalchemy.orm import Session

from app.ai import get_ai_status
from app.config import CORS_ALLOW_ORIGINS, DEBUG, ENV
from app.db import get_db, init_db
from app.models import (
    AIStatus,
    DeviceToken,
    DeviceTokenRegister,
    Game,
    GameCreate,
    GameEvent,
    GameInvite,
    GameRoundCreate,
    GameStats,
    GuessCreate,
    GuessResult,
    InviteCreate,
    InviteJoin,
    RetryGenerationRequest,
    Round,
    RoundCreate,
    TestNotificationRequest,
    TestNotificationResponse,
    User,
    UserCreate,
    UserUpdate,
)
from app import services

logger = logging.getLogger("ai_pictionary.api")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


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


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.exception("request.failed", extra={"request_id": request_id, "path": request.url.path})
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
            "path": request.url.path,
            "status_code": response.status_code,
            "elapsed_ms": elapsed_ms,
        },
    )
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def require_debug() -> None:
    if ENV == "production" or not DEBUG:
        raise HTTPException(status_code=404, detail="Not found")


@app.get("/ai/status", response_model=AIStatus)
def ai_status() -> dict:
    return get_ai_status()


@app.get("/debug/health/full")
def debug_health_full(db: Session = Depends(get_db)) -> dict:
    require_debug()
    return {"status": "ok", "env": ENV, "ai": get_ai_status(), "database": "ok"}


@app.get("/debug/events")
def debug_events(limit: int = 100, db: Session = Depends(get_db)) -> list[GameEvent]:
    require_debug()
    return services.list_all_events(db, limit=limit)


@app.get("/debug/games")
def debug_games(limit: int = 100, db: Session = Depends(get_db)) -> list[Game]:
    require_debug()
    return services.list_all_games(db, limit=limit)


@app.get("/debug/notification-outbox")
def debug_notification_outbox(limit: int = 100, db: Session = Depends(get_db)) -> dict:
    require_debug()
    from app.notifications import NOTIFICATION_OUTBOX

    return {
        "outbox": [message.__dict__ for message in NOTIFICATION_OUTBOX[-limit:]],
        "attempts": services.list_notification_attempts(db, limit=limit),
    }


@app.post("/debug/send-test-notification", response_model=TestNotificationResponse)
def debug_send_test_notification(payload: TestNotificationRequest, db: Session = Depends(get_db)) -> TestNotificationResponse:
    require_debug()
    return services.send_debug_test_notification(db, payload.user_id, game_id=payload.game_id)


@app.post("/users", response_model=User, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    return services.create_user(db, payload)


@app.get("/users/{user_id}", response_model=User)
def get_user(user_id: str, db: Session = Depends(get_db)) -> User:
    return services.get_user(db, user_id)


@app.patch("/users/{user_id}", response_model=User)
def update_user(user_id: str, payload: UserUpdate, db: Session = Depends(get_db)) -> User:
    return services.update_user(db, user_id, payload)


@app.post("/games", response_model=Game, status_code=201)
def create_game(payload: GameCreate, db: Session = Depends(get_db)) -> Game:
    return services.create_game(db, payload)


@app.get("/users/{user_id}/games", response_model=list[Game])
def list_games(user_id: str, db: Session = Depends(get_db)) -> list[Game]:
    return services.list_games_for_user(db, user_id)


@app.get("/games/{game_id}", response_model=Game)
def get_game(game_id: str, user_id: Optional[str] = None, db: Session = Depends(get_db)) -> Game:
    return services.get_game(db, game_id, user_id=user_id)


@app.get("/games/{game_id}/stats", response_model=GameStats)
def get_game_stats(game_id: str, user_id: str, db: Session = Depends(get_db)) -> GameStats:
    return services.get_game_stats(db, game_id, user_id=user_id)


@app.get("/games/{game_id}/events", response_model=list[GameEvent])
def get_game_events(game_id: str, after_id: int = 0, db: Session = Depends(get_db)) -> list[GameEvent]:
    return services.list_events(db, game_id, after_id=after_id)


@app.post("/invites", response_model=GameInvite, status_code=201)
def create_invite(payload: InviteCreate, db: Session = Depends(get_db)) -> GameInvite:
    return services.create_invite(db, payload)


@app.get("/invites/{code}", response_model=GameInvite)
def get_invite(code: str, db: Session = Depends(get_db)) -> GameInvite:
    return services.get_invite(db, code)


@app.post("/invites/{code}/join", response_model=Game, status_code=201)
def join_invite(code: str, payload: InviteJoin, db: Session = Depends(get_db)) -> Game:
    return services.join_invite(db, code, payload)


@app.post("/device-tokens", response_model=DeviceToken, status_code=201)
def register_device_token(payload: DeviceTokenRegister, db: Session = Depends(get_db)) -> DeviceToken:
    return services.register_device_token(db, payload)


@app.post("/games/{game_id}/rounds", response_model=Round, status_code=201)
async def create_game_round(
    game_id: str,
    payload: GameRoundCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Round:
    if DEBUG:
        logger.info("request.payload", extra={"game_id": game_id, "payload": payload.model_dump()})
    round_record = services.create_round_for_game(db, game_id, payload)
    background_tasks.add_task(services.generate_round_svgs, round_record.id)
    return round_record


@app.post("/rounds", response_model=Round, status_code=201)
async def create_round_endpoint(payload: RoundCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> Round:
    round_record = services.create_legacy_round(db, payload)
    background_tasks.add_task(services.generate_round_svgs, round_record.id)
    return round_record


@app.get("/rounds/{round_id}", response_model=Round)
def get_round(round_id: str, user_id: Optional[str] = None, db: Session = Depends(get_db)) -> Round:
    return services.get_round_for_user(db, round_id, user_id=user_id)


@app.post("/rounds/{round_id}/retry-generation", response_model=Round)
async def retry_round_generation(
    round_id: str,
    payload: RetryGenerationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Round:
    round_record = services.prepare_generation_retry(db, round_id, payload.user_id)
    background_tasks.add_task(services.generate_round_svgs, round_id)
    return round_record


@app.post("/rounds/{round_id}/guess", response_model=GuessResult)
async def guess_round(round_id: str, payload: GuessCreate, db: Session = Depends(get_db)) -> GuessResult:
    return services.submit_guess(
        db,
        round_id,
        payload.guess_text,
        user_id=payload.user_id,
        clue_count_used=payload.clue_count_used,
    )


@app.websocket("/ws/games/{game_id}")
async def game_events_websocket(websocket: WebSocket, game_id: str) -> None:
    await websocket.accept()
    last_event_id = int(websocket.query_params.get("after_id", "0"))
    user_id = websocket.query_params.get("user_id")
    try:
        with services.SessionLocal() as db:
            game = db.get(services.GameORM, game_id)
            if not game:
                await websocket.send_json({"type": "error", "message": "Game not found"})
                await websocket.close(code=1008)
                return
            if user_id:
                services.require_game_participant(game, user_id)
        await websocket.send_json({"type": "connected", "game_id": game_id, "after_id": last_event_id})
        logger.info("websocket.connected", extra={"game_id": game_id, "user_id": user_id})
        while True:
            with services.SessionLocal() as db:
                events = services.list_events(db, game_id, after_id=last_event_id)
            for event in events:
                last_event_id = event.id
                await websocket.send_json({"type": "event", "event": event.model_dump()})
            await asyncio.sleep(0.75)
    except WebSocketDisconnect:
        logger.info("websocket.disconnected", extra={"game_id": game_id, "user_id": user_id})
        return
    except HTTPException:
        await websocket.send_json({"type": "error", "message": "Not allowed"})
        await websocket.close(code=1008)
