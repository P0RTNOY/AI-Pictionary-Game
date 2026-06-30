from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class RoundStatus(str, Enum):
    generating = "generating"
    ready_to_guess = "ready_to_guess"
    guessed = "guessed"
    failed = "failed"


class SvgStatus(str, Enum):
    pending = "pending"
    done = "done"
    failed = "failed"


class RoundCreate(BaseModel):
    prompt: str = Field(min_length=6, max_length=240)
    creator_user_id: str = "local-player-1"
    guesser_user_id: str = "local-player-2"


class GeneratedSvg(BaseModel):
    id: str
    model_name: str
    model_tier: str
    svg_text: Optional[str] = None
    generation_time_seconds: Optional[float] = None
    status: SvgStatus = SvgStatus.pending
    error_message: Optional[str] = None


class Round(BaseModel):
    id: str
    creator_user_id: str
    guesser_user_id: str
    original_prompt: str
    status: RoundStatus
    generated_svgs: list[GeneratedSvg]
    created_at: str
    completed_at: Optional[str] = None
    guess: Optional["GuessResult"] = None


class GuessCreate(BaseModel):
    guess_text: str = Field(min_length=2, max_length=240)


class GuessResult(BaseModel):
    round_id: str
    guess_text: str
    score: int = Field(ge=0, le=100)
    matched_parts: list[str]
    missed_parts: list[str]
    short_feedback: str
    judge_result_json: dict[str, Any]
    created_at: str


Round.model_rebuild()
