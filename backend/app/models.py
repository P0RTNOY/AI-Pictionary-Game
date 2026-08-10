from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class RoundStatus(str, Enum):
    generating = "generating"
    ready_to_guess = "ready_to_guess"
    guessed = "guessed"
    failed = "failed"


class SvgStatus(str, Enum):
    pending = "pending"
    generating = "generating"
    done = "done"
    failed = "failed"


class GameStatus(str, Enum):
    active = "active"
    completed = "completed"
    archived = "archived"


class InviteStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    expired = "expired"


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(default="Local Player", min_length=1, max_length=80)
    avatar_url: Optional[str] = None
    avatar_emoji: str = Field(default="🙂", min_length=1, max_length=8)
    avatar_color: str = Field(default="#F5C84C", min_length=4, max_length=16)


class UserUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    avatar_emoji: Optional[str] = Field(default=None, min_length=1, max_length=8)
    avatar_color: Optional[str] = Field(default=None, min_length=4, max_length=16)


class User(BaseModel):
    id: str
    display_name: str
    avatar_url: Optional[str] = None
    avatar_emoji: str = "🙂"
    avatar_color: str = "#F5C84C"
    auth_provider: Optional[str] = None
    auth_subject: Optional[str] = None
    created_at: str
    updated_at: str


class UserSession(BaseModel):
    user: User
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class GameCreate(BaseModel):
    player_1_id: str
    player_2_id: str


class Game(BaseModel):
    id: str
    player_1_id: str
    player_2_id: str
    current_turn_user_id: str
    status: GameStatus
    created_at: str
    updated_at: str
    latest_round: Optional["Round"] = None
    opponent: Optional[User] = None


class GameStats(BaseModel):
    game_id: str
    rounds_played: int
    total_score_by_user: dict[str, int]
    average_score_by_user: dict[str, float]
    best_score: Optional[int] = None
    current_turn_user_id: str
    last_activity_at: str


class RoundCreate(BaseModel):
    prompt: str = Field(min_length=6, max_length=240)
    creator_user_id: str = "local-player-1"
    guesser_user_id: str = "local-player-2"


class GameRoundCreate(BaseModel):
    prompt: str = Field(min_length=6, max_length=240)
    creator_user_id: Optional[str] = None


class GeneratedSvg(BaseModel):
    id: str
    model_name: str
    model_tier: str
    provider_used: Optional[str] = None
    svg_text: Optional[str] = None
    generation_time_seconds: Optional[float] = None
    status: SvgStatus = SvgStatus.pending
    error_message: Optional[str] = None
    attempts: int = 0


class Round(BaseModel):
    id: str
    game_id: str
    creator_user_id: str
    guesser_user_id: str
    original_prompt: str
    status: RoundStatus
    generated_svgs: list[GeneratedSvg]
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None
    clue_reveal_count: int = 1
    guess: Optional["GuessResult"] = None


class GuessCreate(BaseModel):
    guess_text: str = Field(min_length=2, max_length=240)
    user_id: Optional[str] = None
    clue_count_used: int = Field(default=1, ge=1, le=3)


class RetryGenerationRequest(BaseModel):
    user_id: Optional[str] = None


class GuessResult(BaseModel):
    round_id: str
    guess_text: str
    score: int = Field(ge=0, le=100)
    matched_parts: list[str]
    missed_parts: list[str]
    short_feedback: str
    judge_result_json: dict[str, Any]
    component_scores: dict[str, int] = Field(default_factory=dict)
    clue_count_used: int = 1
    clue_penalty: int = 0
    created_at: str


class GameEvent(BaseModel):
    id: int
    game_id: str
    user_id: Optional[str] = None
    event_type: str
    payload: dict[str, Any]
    created_at: str


class InviteCreate(BaseModel):
    creator_user_id: Optional[str] = None
    expires_in_hours: int = Field(default=72, ge=1, le=24 * 14)


class GameInvite(BaseModel):
    code: str
    creator_user_id: str
    game_id: Optional[str] = None
    status: InviteStatus
    expires_at: str
    accepted_by_user_id: Optional[str] = None
    accepted_at: Optional[str] = None
    created_at: str
    updated_at: str


class GameInvitePreview(BaseModel):
    code: str
    creator_user_id: str
    status: InviteStatus
    expires_at: str


class InviteCodeRequest(BaseModel):
    code: str = Field(min_length=16, max_length=64)


class InviteJoin(BaseModel):
    user_id: Optional[str] = None


class InviteJoinRequest(InviteCodeRequest):
    user_id: Optional[str] = None


class WebSocketTicket(BaseModel):
    ticket: str
    expires_at: str


class DeviceTokenRegister(BaseModel):
    user_id: Optional[str] = None
    token: str = Field(min_length=8, max_length=500)
    provider: str = Field(default="expo", min_length=2, max_length=40)
    platform: str = Field(default="unknown", min_length=2, max_length=40)


class DeviceToken(BaseModel):
    id: str
    user_id: str
    provider: str
    token: str
    platform: str
    status: str
    created_at: str
    updated_at: str


class TestNotificationRequest(BaseModel):
    user_id: str
    game_id: Optional[str] = None


class TestNotificationResponse(BaseModel):
    user_id: str
    queued: bool
    active_device_tokens: int
    provider: str


class NotificationAttempt(BaseModel):
    id: str
    user_id: str
    device_token_id: Optional[str] = None
    provider: str
    title: str
    body: str
    payload: dict[str, Any]
    status: str
    response: dict[str, Any]
    error_message: Optional[str] = None
    created_at: str


class AIStatus(BaseModel):
    runtime_provider: str
    openrouter_configured: bool
    local_model_configured: bool
    mock_mode_notice: Optional[str] = None
    artist_models: list[dict[str, Any]]
    judge_model: str


Round.model_rebuild()
Game.model_rebuild()
