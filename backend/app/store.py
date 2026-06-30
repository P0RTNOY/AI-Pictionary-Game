from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone

from app.ai import ARTIST_MODELS, generate_artist_svg, score_guess
from app.models import GeneratedSvg, GuessResult, Round, RoundCreate, RoundStatus, SvgStatus


ROUNDS: dict[str, Round] = {}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_round(payload: RoundCreate) -> Round:
    round_id = str(uuid.uuid4())
    round_record = Round(
        id=round_id,
        creator_user_id=payload.creator_user_id,
        guesser_user_id=payload.guesser_user_id,
        original_prompt=payload.prompt.strip(),
        status=RoundStatus.generating,
        generated_svgs=[
            GeneratedSvg(
                id=str(uuid.uuid4()),
                model_name=model["model"],
                model_tier=model["tier"],
            )
            for model in ARTIST_MODELS
        ],
        created_at=now_iso(),
    )
    ROUNDS[round_id] = round_record
    return round_record


async def generate_round_svgs(round_id: str) -> None:
    round_record = ROUNDS[round_id]

    async def generate_one(index: int, model_config: dict[str, str | None]) -> None:
        started = time.perf_counter()
        try:
            svg_text = await generate_artist_svg(round_record.original_prompt, model_config)
            round_record.generated_svgs[index].svg_text = svg_text
            round_record.generated_svgs[index].status = SvgStatus.done
        except Exception as exc:
            round_record.generated_svgs[index].status = SvgStatus.failed
            round_record.generated_svgs[index].error_message = str(exc)
        finally:
            round_record.generated_svgs[index].generation_time_seconds = round(time.perf_counter() - started, 2)

    await asyncio.gather(*(generate_one(index, model) for index, model in enumerate(ARTIST_MODELS)))
    if any(svg.status == SvgStatus.done for svg in round_record.generated_svgs):
        round_record.status = RoundStatus.ready_to_guess
    else:
        round_record.status = RoundStatus.failed


async def submit_guess(round_id: str, guess_text: str) -> GuessResult:
    round_record = ROUNDS[round_id]
    judge = await score_guess(round_record.original_prompt, guess_text)
    result = GuessResult(
        round_id=round_id,
        guess_text=guess_text.strip(),
        score=int(judge["score"]),
        matched_parts=judge["matched_parts"],
        missed_parts=judge["missed_parts"],
        short_feedback=judge["short_feedback"],
        judge_result_json=judge,
        created_at=now_iso(),
    )
    round_record.guess = result
    round_record.status = RoundStatus.guessed
    round_record.completed_at = now_iso()
    return result
