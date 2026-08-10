from __future__ import annotations

import os
import tempfile
from pathlib import Path

from app.db import engine
from conftest import TEST_DATABASE_DIRECTORY, TEST_DATABASE_PATH, assert_dedicated_test_database


def test_harness_uses_only_its_dedicated_sqlite_database() -> None:
    assert_dedicated_test_database()
    inherited_url = os.environ["AI_PICTIONARY_INHERITED_DATABASE_URL"]
    engine_path = Path(str(engine.url.database)).resolve()

    assert engine.url.get_backend_name() == "sqlite"
    assert TEST_DATABASE_DIRECTORY.parent == Path(tempfile.gettempdir()).resolve()
    assert TEST_DATABASE_DIRECTORY.name.startswith("ai-pictionary-pytest-only-")
    assert TEST_DATABASE_DIRECTORY.is_dir()
    assert not TEST_DATABASE_DIRECTORY.is_symlink()
    assert TEST_DATABASE_PATH.parent == TEST_DATABASE_DIRECTORY
    assert engine_path == TEST_DATABASE_PATH
    assert str(engine.url) != inherited_url
    assert "DATABASE_URL" not in os.environ
    assert os.environ["ENV"] == "test"
    assert os.environ["AUTO_CREATE_TABLES"] == "false"
    assert os.environ["AI_PROVIDER"] == "mock"
    assert os.environ["NOTIFICATION_PROVIDER"] == "mock"
    assert os.environ["PYTHON_DOTENV_DISABLED"] == "1"
