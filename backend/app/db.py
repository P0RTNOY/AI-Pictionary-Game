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
    if "generated_svgs" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("generated_svgs")}
        if "provider_used" not in existing:
            statements.append("ALTER TABLE generated_svgs ADD COLUMN provider_used VARCHAR(40)")
    with bind.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
