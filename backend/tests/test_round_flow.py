import pytest

from app.models import RoundCreate, RoundStatus
from app.store import ROUNDS, create_round, generate_round_svgs, submit_guess


@pytest.mark.asyncio
async def test_round_generation_and_guess_flow():
    ROUNDS.clear()
    round_record = create_round(RoundCreate(prompt="a giraffe teaching a dolphin piano"))

    assert round_record.status == RoundStatus.generating

    await generate_round_svgs(round_record.id)
    generated = ROUNDS[round_record.id]

    assert generated.status == RoundStatus.ready_to_guess
    assert len(generated.generated_svgs) == 3
    assert all(svg.svg_text for svg in generated.generated_svgs)

    result = await submit_guess(round_record.id, "giraffe gives dolphin piano lesson")

    assert result.score >= 50
    assert ROUNDS[round_record.id].status == RoundStatus.guessed
