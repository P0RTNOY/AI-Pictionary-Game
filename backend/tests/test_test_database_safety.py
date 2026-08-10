from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
PROBE_PATH = BACKEND_DIRECTORY / "tests" / "harness_database_probe.py"


def run_harness_probe(inherited_url: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "AI_PICTIONARY_INHERITED_DATABASE_URL": inherited_url,
            "DATABASE_URL": inherited_url,
            "ENV": "production",
            "DEBUG": "false",
            "AUTO_CREATE_TABLES": "true",
            "AI_PROVIDER": "openrouter",
            "NOTIFICATION_PROVIDER": "expo",
            "PYTHON_DOTENV_DISABLED": "0",
        }
    )
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(PROBE_PATH)],
        cwd=BACKEND_DIRECTORY,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def assert_probe_passed(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, f"probe failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"


def test_inherited_application_sqlite_database_is_never_used(tmp_path: Path) -> None:
    application_database = tmp_path / "sentinel-application.sqlite3"
    with sqlite3.connect(application_database) as connection:
        connection.execute("PRAGMA user_version = 917")
        connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel (value) VALUES ('must survive unchanged')")
    original_bytes = application_database.read_bytes()

    result = run_harness_probe(f"sqlite:///{application_database}")

    assert_probe_passed(result)
    assert application_database.read_bytes() == original_bytes
    with sqlite3.connect(application_database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (917,)
        assert connection.execute("SELECT value FROM sentinel").fetchone() == ("must survive unchanged",)
        assert connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall() == [("sentinel",)]


def test_inherited_non_sqlite_database_url_is_overridden_without_connecting() -> None:
    unreachable_application_url = "postgresql+psycopg://do-not-connect.invalid:1/application"

    result = run_harness_probe(unreachable_application_url)

    assert_probe_passed(result)
