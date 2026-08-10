from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import services
from app.db import SessionLocal
from app.main import app
from app.models import GameCreate, GameRoundCreate, RoundStatus, SvgStatus, UserCreate
from app.orm_models import GeneratedSvg as GeneratedSvgORM
from app.orm_models import Guess as GuessORM
from app.orm_models import Round as RoundORM


def _ready_round(db):
    creator = services.create_user(db, UserCreate(display_name="Clue creator"))
    guesser = services.create_user(db, UserCreate(display_name="Clue guesser"))
    game = services.create_game(db, GameCreate(player_1_id=creator.id, player_2_id=guesser.id))
    created = services.create_round_for_game(
        db,
        game.id,
        GameRoundCreate(prompt="a penguin painting a lighthouse", creator_user_id=creator.id),
    )
    stored = services.load_round_orm(db, created.id)
    stored.status = RoundStatus.ready_to_guess.value
    for index, svg in enumerate(stored.generated_svgs):
        svg.status = SvgStatus.done.value
        svg.svg_text = f"<svg><text>{index}</text></svg>"
    db.commit()
    return creator, guesser, stored


def test_missing_environment_is_production_shaped_and_startup_does_not_create_schema(tmp_path):
    database_path = tmp_path / "missing-env.sqlite3"
    script = """
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from app.config import AUTO_CREATE_TABLES, CORS_ALLOW_ORIGINS, DEBUG, ENV
from app.db import engine
from app.main import app
assert ENV == 'production'
assert DEBUG is False
assert AUTO_CREATE_TABLES is False
assert '*' not in CORS_ALLOW_ORIGINS
with TestClient(app) as client:
    assert client.get('/debug/health/full').status_code == 404
assert inspect(engine).get_table_names() == []
"""
    environment = os.environ.copy()
    for name in ("ENV", "DEBUG", "AUTO_CREATE_TABLES", "CORS_ALLOW_ORIGINS"):
        environment.pop(name, None)
    environment.update(
        {
            "DATABASE_URL": f"sqlite:///{database_path}",
            "PYTHON_DOTENV_DISABLED": "1",
            "PYTHONPATH": str(Path(__file__).parents[1]),
        }
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[1],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr


def test_unknown_environment_cannot_enable_debug_or_auto_schema_creation(tmp_path):
    database_path = tmp_path / "unknown-env.sqlite3"
    script = """
from sqlalchemy import inspect
from app.config import AUTO_CREATE_TABLES, CORS_ALLOW_ORIGINS, DEBUG
from app.db import init_db, engine
assert DEBUG is False
assert AUTO_CREATE_TABLES is False
assert '*' not in CORS_ALLOW_ORIGINS
init_db()
assert inspect(engine).get_table_names() == []
"""
    environment = os.environ.copy()
    environment.update(
        {
            "ENV": "unexpected",
            "DEBUG": "true",
            "AUTO_CREATE_TABLES": "true",
            "CORS_ALLOW_ORIGINS": "*",
            "DATABASE_URL": f"sqlite:///{database_path}",
            "PYTHON_DOTENV_DISABLED": "1",
            "PYTHONPATH": str(Path(__file__).parents[1]),
        }
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[1],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr


def test_sqlite_connections_enforce_foreign_keys_and_have_no_violations(db_session):
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO games (id, player_1_id, player_2_id, current_turn_user_id, status, created_at, updated_at) "
                "VALUES ('orphan', 'missing-1', 'missing-2', 'missing-1', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        db_session.commit()
    db_session.rollback()
    assert db_session.execute(text("PRAGMA foreign_key_check")).all() == []


def test_reset_prevents_stale_generation_from_repopulating_orphan_rows(db_session):
    _, _, round_record = _ready_round(db_session)
    stale_round_id = round_record.id
    db_session.close()

    with SessionLocal() as reset_session:
        result = services.reset_local_data(reset_session)
        assert result.deleted_rows > 0

    with SessionLocal() as stale_generation_session:
        stale_generation_session.add(
            GeneratedSvgORM(
                id=services.new_id(),
                round_id=stale_round_id,
                sort_order=99,
                model_name="stale-background-worker",
                model_tier="test",
                status=SvgStatus.done.value,
                svg_text="<svg/>",
            )
        )
        with pytest.raises(IntegrityError):
            stale_generation_session.commit()
        stale_generation_session.rollback()
        assert stale_generation_session.execute(text("PRAGMA foreign_key_check")).all() == []
        assert stale_generation_session.scalar(select(func.count()).select_from(RoundORM)) == 0
        assert stale_generation_session.scalar(select(func.count()).select_from(GeneratedSvgORM)) == 0


def test_device_token_migration_uses_revision_local_limit():
    migration = Path(__file__).parents[1] / "alembic/versions/20260810_0004_device_token_ownership.py"
    source = migration.read_text()
    assert "from app.config import ACTIVE_DEVICE_TOKEN_LIMIT" not in source
    assert "ACTIVE_DEVICE_TOKEN_LIMIT = 3" in source


def test_backend_container_contains_explicit_migration_runtime():
    dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()
    assert "COPY alembic.ini ." in dockerfile
    assert "COPY alembic ./alembic" in dockerfile
    assert "alembic upgrade head" not in dockerfile


def test_reveal_clue_is_guesser_only_bounded_and_guess_ignores_client_count(db_session):
    creator, guesser, round_record = _ready_round(db_session)

    with pytest.raises(HTTPException) as forbidden:
        services.reveal_next_clue(db_session, round_record.id, creator.id)
    assert forbidden.value.status_code == 403

    second = services.reveal_next_clue(db_session, round_record.id, guesser.id)
    assert second.clue_reveal_count == 2
    third = services.reveal_next_clue(db_session, round_record.id, guesser.id)
    assert third.clue_reveal_count == 3
    with pytest.raises(HTTPException) as exhausted:
        services.reveal_next_clue(db_session, round_record.id, guesser.id)
    assert exhausted.value.status_code == 409

    result = services.submit_guess(
        db_session,
        round_record.id,
        "penguin painting lighthouse",
        user_id=guesser.id,
        clue_count_used=1,
    )
    assert result.clue_count_used == 3
    assert result.clue_penalty == 16


def test_authenticated_reveal_endpoint_denies_non_guesser(db_session):
    creator_session = services.create_user_session(db_session, UserCreate(display_name="API creator"))
    guesser_session = services.create_user_session(db_session, UserCreate(display_name="API guesser"))
    game = services.create_game(
        db_session,
        GameCreate(player_1_id=creator_session.user.id, player_2_id=guesser_session.user.id),
    )
    created = services.create_round_for_game(
        db_session,
        game.id,
        GameRoundCreate(prompt="a penguin painting a lighthouse", creator_user_id=creator_session.user.id),
    )
    stored = services.load_round_orm(db_session, created.id)
    stored.status = RoundStatus.ready_to_guess.value
    for svg in stored.generated_svgs:
        svg.status = SvgStatus.done.value
        svg.svg_text = "<svg/>"
    db_session.commit()

    with TestClient(app) as client:
        creator_response = client.post(
            f"/rounds/{created.id}/reveal-clue",
            headers={"Authorization": f"Bearer {creator_session.access_token}"},
        )
        guesser_response = client.post(
            f"/rounds/{created.id}/reveal-clue",
            headers={"Authorization": f"Bearer {guesser_session.access_token}"},
        )
    assert creator_response.status_code == 403
    assert guesser_response.status_code == 200
    assert guesser_response.json()["clue_reveal_count"] == 2


def test_concurrent_reveals_never_exceed_completed_clues(db_session):
    _, guesser, round_record = _ready_round(db_session)
    round_id = round_record.id
    guesser_id = guesser.id
    db_session.close()

    def reveal():
        with SessionLocal() as db:
            try:
                return ("ok", services.reveal_next_clue(db, round_id, guesser_id).clue_reveal_count)
            except HTTPException as exc:
                return ("error", exc.status_code)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: reveal(), range(4)))

    with SessionLocal() as verification:
        stored = verification.get(RoundORM, round_id)
        assert stored is not None
        assert stored.clue_reveal_count == 3
    assert sorted(value for status, value in results if status == "ok") == [2, 3]
    assert all(value == 409 for status, value in results if status == "error")


def test_submit_and_reveal_race_records_one_linearizable_clue_count(db_session):
    _, guesser, round_record = _ready_round(db_session)
    round_id = round_record.id
    guesser_id = guesser.id
    db_session.close()

    def reveal():
        with SessionLocal() as db:
            try:
                return ("reveal", services.reveal_next_clue(db, round_id, guesser_id).clue_reveal_count)
            except HTTPException as exc:
                return ("reveal-error", exc.status_code)

    def submit():
        with SessionLocal() as db:
            result = services.submit_guess(db, round_id, "penguin painting lighthouse", user_id=guesser_id, clue_count_used=3)
            return ("submit", result.clue_count_used)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(reveal), pool.submit(submit)]
        outcomes = [future.result() for future in results]

    with SessionLocal() as verification:
        stored_round = verification.get(RoundORM, round_id)
        stored_guess = verification.scalar(select(GuessORM).where(GuessORM.round_id == round_id))
        assert stored_round is not None and stored_guess is not None
        assert stored_round.clue_reveal_count == stored_guess.clue_count_used
        assert stored_guess.clue_count_used in (1, 2)
    assert any(kind == "submit" for kind, _ in outcomes)
