from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import AUTO_CREATE_TABLES, DATABASE_URL


connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from app import orm_models  # noqa: F401

    if AUTO_CREATE_TABLES:
        Base.metadata.create_all(bind=engine)
    if DATABASE_URL.startswith("sqlite"):
        _apply_sqlite_light_migrations()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _apply_sqlite_light_migrations(bind=engine) -> None:
    inspector = inspect(bind)
    statements = []
    if "users" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("users")}
        if "avatar_emoji" not in existing:
            statements.append("ALTER TABLE users ADD COLUMN avatar_emoji VARCHAR(16) NOT NULL DEFAULT '🙂'")
        if "avatar_color" not in existing:
            statements.append("ALTER TABLE users ADD COLUMN avatar_color VARCHAR(16) NOT NULL DEFAULT '#F5C84C'")
        if "auth_provider" not in existing:
            statements.append("ALTER TABLE users ADD COLUMN auth_provider VARCHAR(40)")
        if "auth_subject" not in existing:
            statements.append("ALTER TABLE users ADD COLUMN auth_subject VARCHAR(160)")
        if "session_token_hash" not in existing:
            statements.append("ALTER TABLE users ADD COLUMN session_token_hash VARCHAR(64)")
        statements.append(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_session_token_hash ON users (session_token_hash)"
        )
    if "generated_svgs" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("generated_svgs")}
        if "provider_used" not in existing:
            statements.append("ALTER TABLE generated_svgs ADD COLUMN provider_used VARCHAR(40)")
    if "guesses" in inspector.get_table_names():
        statements.extend(
            [
                "CREATE TABLE IF NOT EXISTS task3_guess_conflict_archive ("
                "id VARCHAR(64) PRIMARY KEY, round_id VARCHAR(64) NOT NULL, user_id VARCHAR(64) NOT NULL, "
                "guess_text TEXT NOT NULL, score INTEGER NOT NULL, judge_result_json TEXT NOT NULL, "
                "component_scores_json TEXT NOT NULL, clue_count_used INTEGER NOT NULL, "
                "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)",
                "INSERT OR IGNORE INTO task3_guess_conflict_archive "
                "(id, round_id, user_id, guess_text, score, judge_result_json, component_scores_json, "
                "clue_count_used, created_at, updated_at) "
                "SELECT id, round_id, user_id, guess_text, score, judge_result_json, component_scores_json, "
                "clue_count_used, created_at, updated_at FROM ("
                "SELECT guesses.*, ROW_NUMBER() OVER (PARTITION BY round_id ORDER BY created_at ASC, id ASC) task3_rank "
                "FROM guesses) ranked WHERE task3_rank > 1",
                "DELETE FROM guesses WHERE id IN (SELECT id FROM task3_guess_conflict_archive)",
            ]
        )
        statements.append("CREATE UNIQUE INDEX IF NOT EXISTS uq_guesses_round_id ON guesses (round_id)")
    if "rounds" in inspector.get_table_names():
        statements.extend(
            [
                "CREATE TABLE IF NOT EXISTS task3_active_round_archive ("
                "round_id VARCHAR(64) PRIMARY KEY, original_status VARCHAR(40) NOT NULL)",
                "INSERT OR IGNORE INTO task3_active_round_archive (round_id, original_status) "
                "SELECT id, status FROM (SELECT id, status, ROW_NUMBER() OVER ("
                "PARTITION BY game_id ORDER BY created_at ASC, id ASC) task3_rank FROM rounds "
                "WHERE status IN ('generating', 'ready_to_guess')) ranked WHERE task3_rank > 1",
                "UPDATE rounds SET status = 'failed' WHERE id IN (SELECT round_id FROM task3_active_round_archive)",
            ]
        )
        statements.append(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_rounds_one_active_per_game ON rounds (game_id) "
            "WHERE status IN ('generating', 'ready_to_guess')"
        )
    if "generation_admission_gate" in inspector.get_table_names():
        statements.append(
            "INSERT INTO generation_admission_gate (id, version) VALUES (1, 0) ON CONFLICT(id) DO NOTHING"
        )
    with bind.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
