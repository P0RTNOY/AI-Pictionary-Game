from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock
from datetime import timedelta

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select, text

from app import services
from app.db import SessionLocal
from app.main import app
from app.models import GameCreate, GameRoundCreate, RoundStatus, SvgStatus, UserCreate
from app.orm_models import Guess as GuessORM
from app.orm_models import Round as RoundORM


def ready_round(db):
    creator = services.create_user_session(db, UserCreate(display_name="Judge creator"))
    guesser = services.create_user_session(db, UserCreate(display_name="Judge guesser"))
    game = services.create_game(
        db,
        GameCreate(player_1_id=creator.user.id, player_2_id=guesser.user.id),
    )
    created = services.create_round_for_game(
        db,
        game.id,
        GameRoundCreate(prompt="a penguin painting a lighthouse", creator_user_id=creator.user.id),
    )
    stored = services.load_round_orm(db, created.id)
    stored.status = RoundStatus.ready_to_guess.value
    for svg in stored.generated_svgs:
        svg.status = SvgStatus.done.value
        svg.svg_text = "<svg/>"
    db.commit()
    return creator, guesser, game, stored


def judge_result(score: int = 88):
    return {
        "score": score,
        "matched_parts": ["penguin", "lighthouse"],
        "missed_parts": [],
        "short_feedback": "Strong guess.",
        "component_scores": {"characters": 36, "action": 28, "setting": 16, "twist": 8},
    }


class BlockingJudge:
    name = "blocking"

    def __init__(self):
        self.entered = Event()
        self.release = Event()
        self._lock = Lock()
        self.calls = 0

    def score_guess_sync(self, _original, _guess):
        with self._lock:
            self.calls += 1
        self.entered.set()
        assert self.release.wait(timeout=10)
        return judge_result()


def test_stalled_judge_releases_database_write_lock_and_duplicate_claim_is_immediate(db_session, monkeypatch):
    _, guesser, _, round_record = ready_round(db_session)
    round_id = round_record.id
    guesser_id = guesser.user.id
    db_session.close()
    provider = BlockingJudge()
    monkeypatch.setattr(services, "get_ai_provider", lambda: provider)

    def submit():
        with SessionLocal() as db:
            return services.submit_guess(db, round_id, "penguin painting lighthouse", user_id=guesser_id)

    def write_unrelated_row():
        with SessionLocal() as db:
            return services.create_user(db, UserCreate(display_name="Concurrent writer")).id

    def duplicate():
        with SessionLocal() as db:
            try:
                services.submit_guess(db, round_id, "duplicate guess", user_id=guesser_id)
            except HTTPException as exc:
                return exc.status_code
        return 200

    with ThreadPoolExecutor(max_workers=3) as pool:
        submitted = pool.submit(submit)
        assert provider.entered.wait(timeout=5)
        writer = pool.submit(write_unrelated_row)
        duplicate_result = pool.submit(duplicate)
        try:
            assert writer.result(timeout=1)
            assert duplicate_result.result(timeout=1) == 409
        finally:
            provider.release.set()
        result = submitted.result(timeout=5)

    assert result.score == 88
    assert provider.calls == 1
    with SessionLocal() as verification:
        assert verification.scalar(select(func.count()).select_from(GuessORM)) == 1
        stored = verification.get(RoundORM, round_id)
        assert stored is not None
        assert stored.status == RoundStatus.guessed.value
        assert stored.guess_claim_id is None


def test_judge_failure_restores_ready_round_for_retry(db_session, monkeypatch):
    _, guesser, _, round_record = ready_round(db_session)

    class FailingJudge:
        name = "failing"

        def score_guess_sync(self, _original, _guess):
            raise RuntimeError("provider details must stay private")

    monkeypatch.setattr(services, "get_ai_provider", lambda: FailingJudge())
    with pytest.raises(HTTPException) as failed:
        services.submit_guess(
            db_session,
            round_record.id,
            "penguin painting lighthouse",
            user_id=guesser.user.id,
        )
    assert failed.value.status_code == 503
    assert failed.value.detail == "Guess scoring failed. Please try again."
    db_session.expire_all()
    stored = db_session.get(RoundORM, round_record.id)
    assert stored is not None
    assert stored.status == RoundStatus.ready_to_guess.value
    assert stored.guess_claim_id is None
    assert db_session.scalar(select(func.count()).select_from(GuessORM)) == 0


def test_finalize_failure_releases_only_its_owned_claim(db_session, monkeypatch):
    _, guesser, _, round_record = ready_round(db_session)

    class SuccessfulJudge:
        name = "successful"

        def score_guess_sync(self, _original, _guess):
            return judge_result()

    def fail_finalize(_db, _claim, _judge):
        raise HTTPException(status_code=409, detail="simulated finalize conflict")

    monkeypatch.setattr(services, "get_ai_provider", lambda: SuccessfulJudge())
    monkeypatch.setattr(services, "finalize_guess_claim", fail_finalize)
    with pytest.raises(HTTPException) as failed:
        services.submit_guess(
            db_session,
            round_record.id,
            "penguin painting lighthouse",
            user_id=guesser.user.id,
        )
    assert failed.value.detail == "simulated finalize conflict"
    db_session.expire_all()
    stored = db_session.get(RoundORM, round_record.id)
    assert stored is not None
    assert stored.status == RoundStatus.ready_to_guess.value
    assert stored.guess_claim_id is None


def test_stale_judging_claim_recovers_after_worker_loss(db_session, monkeypatch):
    _, guesser, _, round_record = ready_round(db_session)
    stored = db_session.get(RoundORM, round_record.id)
    assert stored is not None
    stored.status = RoundStatus.judging.value
    stored.guess_claim_id = "abandoned-claim"
    stored.updated_at = services.now() - timedelta(minutes=5)
    db_session.commit()

    class RecoveryJudge:
        name = "recovery"

        def score_guess_sync(self, _original, _guess):
            return judge_result()

    monkeypatch.setattr(services, "get_ai_provider", lambda: RecoveryJudge())
    result = services.submit_guess(
        db_session,
        round_record.id,
        "penguin painting lighthouse",
        user_id=guesser.user.id,
    )
    assert result.score == 88
    db_session.expire_all()
    recovered = db_session.get(RoundORM, round_record.id)
    assert recovered is not None
    assert recovered.status == RoundStatus.guessed.value
    assert recovered.guess_claim_id is None


def test_sync_guess_route_keeps_health_and_websocket_responsive_during_judging(db_session, monkeypatch):
    _, guesser, game, round_record = ready_round(db_session)
    ticket = services.issue_websocket_ticket(db_session, game.id, guesser.user.id)
    provider = BlockingJudge()
    monkeypatch.setattr(services, "get_ai_provider", lambda: provider)

    with TestClient(app) as client:
        with ThreadPoolExecutor(max_workers=1) as pool:
            submitted = pool.submit(
                client.post,
                f"/rounds/{round_record.id}/guess",
                headers={"Authorization": f"Bearer {guesser.access_token}"},
                json={"guess_text": "penguin painting lighthouse"},
            )
            assert provider.entered.wait(timeout=5)
            try:
                health = client.get("/health")
                assert health.status_code == 200
                with client.websocket_connect(f"/ws/games/{game.id}?ticket={ticket.ticket}&after_id=0") as websocket:
                    connected = websocket.receive_json()
                    assert connected["type"] == "connected"
            finally:
                provider.release.set()
            assert submitted.result(timeout=5).status_code == 200


def test_judging_status_is_part_of_active_round_schema_and_index():
    assert RoundStatus.judging.value == "judging"
    assert hasattr(RoundORM, "guess_claim_id")
    index = next(index for index in RoundORM.__table__.indexes if index.name == "uq_rounds_one_active_per_game")
    assert "judging" in str(index.dialect_options["sqlite"]["where"])


def test_guess_claim_migration_round_trip_restores_inflight_round_to_ready(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'guess-claim-migration.sqlite3'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    migrated = create_engine(database_url)
    with migrated.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, display_name, avatar_emoji, avatar_color, created_at, updated_at) "
                "VALUES ('creator', 'Creator', '1', '#fff', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
                "('guesser', 'Guesser', '2', '#fff', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO games (id, player_1_id, player_2_id, current_turn_user_id, status, created_at, updated_at) "
                "VALUES ('game', 'creator', 'guesser', 'creator', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO rounds (id, game_id, creator_user_id, guesser_user_id, original_prompt, status, "
                "clue_reveal_count, guess_claim_id, created_at, updated_at) VALUES "
                "('round', 'game', 'creator', 'guesser', 'a valid judging prompt', 'judging', 2, 'claim', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )

    command.downgrade(config, "20260810_0005")
    assert "guess_claim_id" not in {column["name"] for column in inspect(migrated).get_columns("rounds")}
    with migrated.connect() as connection:
        assert connection.execute(text("SELECT status FROM rounds WHERE id = 'round'")).scalar_one() == "ready_to_guess"
        previous_index_sql = connection.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'uq_rounds_one_active_per_game'")
        ).scalar_one()
    assert "judging" not in previous_index_sql

    command.upgrade(config, "head")
    assert "guess_claim_id" in {column["name"] for column in inspect(migrated).get_columns("rounds")}
