from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.ai import get_ai_status
from app.models import GuessCreate, GuessResult, Round, RoundCreate, RoundStatus
from app.store import ROUNDS, create_round, generate_round_svgs, submit_guess

app = FastAPI(title="AI Pictionary MVP", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ai/status")
def ai_status() -> dict:
    return get_ai_status()


@app.post("/rounds", response_model=Round, status_code=201)
async def create_round_endpoint(payload: RoundCreate, background_tasks: BackgroundTasks) -> Round:
    round_record = create_round(payload)
    background_tasks.add_task(generate_round_svgs, round_record.id)
    return round_record


@app.get("/rounds", response_model=list[Round])
def list_rounds() -> list[Round]:
    return sorted(ROUNDS.values(), key=lambda item: item.created_at, reverse=True)


@app.get("/rounds/{round_id}", response_model=Round)
def get_round(round_id: str) -> Round:
    if round_id not in ROUNDS:
        raise HTTPException(status_code=404, detail="Round not found")
    return ROUNDS[round_id]


@app.post("/rounds/{round_id}/guess", response_model=GuessResult)
async def guess_round(round_id: str, payload: GuessCreate) -> GuessResult:
    if round_id not in ROUNDS:
        raise HTTPException(status_code=404, detail="Round not found")
    round_record = ROUNDS[round_id]
    if round_record.status not in {RoundStatus.ready_to_guess, RoundStatus.guessed}:
        raise HTTPException(status_code=409, detail="Round is not ready for guesses yet")
    return await submit_guess(round_id, payload.guess_text)
