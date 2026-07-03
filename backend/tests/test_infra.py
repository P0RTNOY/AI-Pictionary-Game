from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import services
from app.config import is_local_env, parse_bool
from app.main import app
from app.models import UserCreate
from app.notifications import ExpoPushNotificationProvider
from app.safety import validate_challenge_prompt


def test_alembic_initial_migration_bootstraps_sqlite(tmp_path, monkeypatch):
    db_path = tmp_path / "migration_smoke.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    assert db_path.exists()
    command.downgrade(config, "base")


def test_expo_push_provider_uses_expo_endpoint(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"status": "ok"}}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def post(self, url, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("app.notifications.httpx.Client", FakeClient)
    result = ExpoPushNotificationProvider().send("ExponentPushToken[test]", "Title", "Body", {"game_id": "g1"})
    assert result["data"]["status"] == "ok"
    assert captured["json"]["to"] == "ExponentPushToken[test]"
    assert captured["json"]["data"]["game_id"] == "g1"


def test_debug_endpoints_enabled_in_development():
    client = TestClient(app)
    response = client.get("/debug/health/full")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_environment_config_helpers_are_safe_by_default():
    assert parse_bool("true") is True
    assert parse_bool("0", default=True) is False
    assert is_local_env("local") is True
    assert is_local_env("development") is True
    assert is_local_env("staging") is False
    assert is_local_env("production") is False


def test_debug_test_notification_endpoint_is_debug_only(monkeypatch, db_session):
    player = services.create_user(db_session, UserCreate(display_name="Push Tester"))
    client = TestClient(app)
    response = client.post("/debug/send-test-notification", json={"user_id": player.id})
    assert response.status_code == 200
    assert response.json()["queued"] is True

    monkeypatch.setattr("app.main.DEBUG", False)
    disabled = client.post("/debug/send-test-notification", json={"user_id": player.id})
    assert disabled.status_code == 404
    monkeypatch.setattr("app.main.DEBUG", True)


def test_prompt_safety_blocks_markup_payloads():
    with pytest.raises(HTTPException):
        validate_challenge_prompt("<script>alert(1)</script>")
