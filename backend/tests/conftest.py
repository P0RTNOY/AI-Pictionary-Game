import os
import tempfile
from pathlib import Path

import pytest

# This must happen before importing app.db: its engine captures DATABASE_URL at
# import time, and the autouse fixture below performs destructive metadata work.
TEST_DATABASE_DIRECTORY = Path(tempfile.mkdtemp(prefix="ai-pictionary-pytest-only-")).resolve()
TEST_DATABASE_PATH = TEST_DATABASE_DIRECTORY / "suite.sqlite3"
os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{TEST_DATABASE_PATH}",
        "ENV": "test",
        "DEBUG": "true",
        "AUTO_CREATE_TABLES": "false",
        "AI_PROVIDER": "mock",
        "NOTIFICATION_PROVIDER": "mock",
        "PYTHON_DOTENV_DISABLED": "1",
    }
)

from app.db import Base, SessionLocal, engine

# Alembic tests provide their own URLs through Config or monkeypatch. Removing
# the bootstrap override prevents the test-suite database from shadowing them,
# while app.db remains permanently bound to the dedicated SQLite engine above.
os.environ.pop("DATABASE_URL", None)


def assert_dedicated_test_database() -> None:
    database_path = engine.url.database
    if (
        engine.url.get_backend_name() != "sqlite"
        or not database_path
        or Path(str(database_path)).resolve() != TEST_DATABASE_PATH
    ):
        raise RuntimeError("Refusing destructive test setup outside the dedicated temporary SQLite database")


@pytest.fixture(autouse=True)
def clean_database(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "mock")
    assert_dedicated_test_database()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    assert_dedicated_test_database()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
