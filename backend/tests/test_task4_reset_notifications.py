from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text

from app import notifications, services
from app.db import SessionLocal, _apply_sqlite_light_migrations
from app.main import app
from app.models import DeviceTokenRegister, GameCreate, GameRoundCreate, UserCreate
from app.orm_models import DeviceToken as DeviceTokenORM
from app.orm_models import DeviceTokenRetirement as DeviceTokenRetirementORM
from app.orm_models import Game as GameORM
from app.orm_models import NotificationAttempt as NotificationAttemptORM
from app.orm_models import User as UserORM


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def onboard(client: TestClient, name: str) -> tuple[dict, str]:
    response = client.post("/users", json={"display_name": name})
    assert response.status_code == 201
    body = response.json()
    return body["user"], body["access_token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("environment", ["staging", "production", "unknown"])
def test_destructive_reset_is_unavailable_in_deployable_or_unknown_environments(
    client, db_session, monkeypatch, environment
):
    user, token = onboard(client, f"Reset {environment}")
    monkeypatch.setattr("app.main.ENV", environment)
    monkeypatch.setattr("app.main.DEBUG", True)

    response = client.post(
        "/debug/reset-local-data",
        headers=bearer(token),
        json={"confirmation": "RESET LOCAL DATA"},
    )

    assert response.status_code == 404
    assert db_session.get(UserORM, user["id"]) is not None


def test_destructive_reset_requires_debug_auth_confirmation_and_clears_all_state(
    client, db_session, monkeypatch
):
    monkeypatch.setattr("app.main.ENV", "test")
    monkeypatch.setattr("app.main.DEBUG", True)
    first, first_token = onboard(client, "Reset Owner")
    second, _ = onboard(client, "Reset Opponent")
    game = services.create_game(
        db_session,
        GameCreate(player_1_id=first["id"], player_2_id=second["id"]),
    )
    services.register_device_token(
        db_session,
        DeviceTokenRegister(
            user_id=first["id"],
            token="ExponentPushToken[reset-owner]",
            platform="ios",
            registration_id="reset-owner-registration",
        ),
    )
    services.create_round_for_game(
        db_session,
        game.id,
        GameRoundCreate(
            prompt="a tiny astronaut watering a cactus",
            creator_user_id=first["id"],
        ),
    )
    assert notifications.NOTIFICATION_OUTBOX

    assert client.post(
        "/debug/reset-local-data", json={"confirmation": "RESET LOCAL DATA"}
    ).status_code == 401
    assert client.post(
        "/debug/reset-local-data",
        headers=bearer(first_token),
        json={"confirmation": "reset please"},
    ).status_code == 422

    response = client.post(
        "/debug/reset-local-data",
        headers=bearer(first_token),
        json={"confirmation": "RESET LOCAL DATA"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["deleted_rows"] > 0
    assert set(response.json()) == {"ok", "deleted_rows"}
    db_session.expire_all()
    for model in (NotificationAttemptORM, DeviceTokenRetirementORM, DeviceTokenORM, GameORM, UserORM):
        assert db_session.scalar(select(func.count()).select_from(model)) == 0
    assert notifications.NOTIFICATION_OUTBOX == []


def test_device_token_has_one_active_owner_limit_and_idempotent_unregister(db_session, monkeypatch):
    monkeypatch.setattr(services, "ACTIVE_DEVICE_TOKEN_LIMIT", 2)
    first = services.create_user(db_session, UserCreate(display_name="First token owner"))
    second = services.create_user(db_session, UserCreate(display_name="Second token owner"))

    first_registration = services.register_device_token(
        db_session,
        DeviceTokenRegister(
            user_id=first.id,
            token="ExponentPushToken[shared-device]",
            platform="ios",
            registration_id="shared-device-first",
        ),
    )
    transferred = services.register_device_token(
        db_session,
        DeviceTokenRegister(
            user_id=second.id,
            token="ExponentPushToken[shared-device]",
            platform="android",
            registration_id="shared-device-second",
        ),
    )

    assert first_registration.token_fingerprint == transferred.token_fingerprint
    assert not hasattr(transferred, "token")
    active_owners = db_session.scalars(
        select(DeviceTokenORM.user_id).where(
            DeviceTokenORM.provider == "expo",
            DeviceTokenORM.token == "ExponentPushToken[shared-device]",
            DeviceTokenORM.status == "active",
        )
    ).all()
    assert active_owners == [second.id]

    for suffix in ("two", "three"):
        services.register_device_token(
            db_session,
            DeviceTokenRegister(
                user_id=second.id,
                token=f"ExponentPushToken[{suffix}]",
                platform="ios",
                registration_id=f"registration-{suffix}",
            ),
        )
    active_count = db_session.scalar(
        select(func.count(DeviceTokenORM.id)).where(
            DeviceTokenORM.user_id == second.id,
            DeviceTokenORM.status == "active",
        )
    )
    assert active_count == 2

    assert services.unregister_device_token(
        db_session, second.id, "expo", "ExponentPushToken[three]", "registration-three"
    ).unregistered is True
    assert services.unregister_device_token(
        db_session, second.id, "expo", "ExponentPushToken[three]", "registration-three"
    ).unregistered is False


def test_registration_generation_prevents_stale_unregister_and_late_register(db_session):
    owner = services.create_user(db_session, UserCreate(display_name="Rotating token owner"))
    raw_token = "ExponentPushToken[generation-guarded]"
    old_registration_id = "registration-old"
    new_registration_id = "registration-new"

    services.register_device_token(
        db_session,
        DeviceTokenRegister(
            user_id=owner.id,
            token=raw_token,
            platform="ios",
            registration_id=old_registration_id,
        ),
    )
    services.register_device_token(
        db_session,
        DeviceTokenRegister(
            user_id=owner.id,
            token=raw_token,
            platform="ios",
            registration_id=new_registration_id,
        ),
    )

    stale = services.unregister_device_token(
        db_session,
        owner.id,
        "expo",
        raw_token,
        old_registration_id,
    )
    assert stale.unregistered is False
    active = db_session.scalar(
        select(DeviceTokenORM).where(
            DeviceTokenORM.user_id == owner.id,
            DeviceTokenORM.token == raw_token,
            DeviceTokenORM.status == "active",
        )
    )
    assert active is not None
    assert active.registration_id == new_registration_id

    late_registration_id = "registration-late"
    retired_before_arrival = services.unregister_device_token(
        db_session,
        owner.id,
        "expo",
        "ExponentPushToken[late-arrival]",
        late_registration_id,
    )
    assert retired_before_arrival.unregistered is False
    with pytest.raises(HTTPException) as exc_info:
        services.register_device_token(
            db_session,
            DeviceTokenRegister(
                user_id=owner.id,
                token="ExponentPushToken[late-arrival]",
                platform="ios",
                registration_id=late_registration_id,
            ),
        )
    assert exc_info.value.status_code == 409
    assert db_session.scalar(
        select(func.count(DeviceTokenORM.id)).where(
            DeviceTokenORM.token == "ExponentPushToken[late-arrival]",
            DeviceTokenORM.status == "active",
        )
    ) == 0


def test_device_token_http_lifecycle_derives_owner_and_never_returns_raw_token(client):
    first, first_token = onboard(client, "First HTTP token owner")
    second, second_token = onboard(client, "Second HTTP token owner")
    raw_token = "ExponentPushToken[http-shared-device]"

    assert client.post(
        "/device-tokens",
        headers=bearer(first_token),
        json={"token": raw_token, "platform": "ios"},
    ).status_code == 422
    assert client.post(
        "/device-tokens/unregister",
        headers=bearer(first_token),
        json={"token": raw_token},
    ).status_code == 422

    forged = client.post(
        "/device-tokens",
        headers=bearer(first_token),
        json={
            "user_id": second["id"],
            "token": raw_token,
            "platform": "ios",
            "registration_id": "forged-owner-registration",
        },
    )
    assert forged.status_code == 403

    first_registration = client.post(
        "/device-tokens",
        headers=bearer(first_token),
        json={"token": raw_token, "platform": "ios", "registration_id": "http-first-registration"},
    )
    transferred = client.post(
        "/device-tokens",
        headers=bearer(second_token),
        json={"token": raw_token, "platform": "android", "registration_id": "http-second-registration"},
    )
    assert first_registration.status_code == 201
    assert transferred.status_code == 201
    assert "token" not in transferred.json()
    assert len(transferred.json()["token_fingerprint"]) == 12
    assert client.post(
        "/device-tokens/unregister",
        headers=bearer(second_token),
        json={"token": raw_token},
    ).status_code == 422

    wrong_owner = client.post(
        "/device-tokens/unregister",
        headers=bearer(first_token),
        json={"token": raw_token, "registration_id": "http-first-registration"},
    )
    owner = client.post(
        "/device-tokens/unregister",
        headers=bearer(second_token),
        json={"token": raw_token, "registration_id": "http-second-registration"},
    )
    assert wrong_owner.json() == {"unregistered": False}
    assert owner.json() == {"unregistered": True}


def test_notification_outbox_and_fanout_are_bounded_and_delivery_is_post_commit(
    db_session, monkeypatch
):
    monkeypatch.setattr(notifications, "NOTIFICATION_OUTBOX_LIMIT", 2)
    monkeypatch.setattr(notifications, "NOTIFICATION_FANOUT_LIMIT", 2)
    notifications.NOTIFICATION_OUTBOX.clear()
    creator = services.create_user(db_session, UserCreate(display_name="Committed Creator"))
    guesser = services.create_user(db_session, UserCreate(display_name="Committed Guesser"))
    game = services.create_game(
        db_session,
        GameCreate(player_1_id=creator.id, player_2_id=guesser.id),
    )
    for suffix in ("a", "b", "c"):
        token = DeviceTokenORM(
            id=services.new_id(),
            user_id=guesser.id,
            provider="expo",
            token=f"ExponentPushToken[{suffix}]",
            platform="ios",
            status="active",
        )
        db_session.add(token)
    db_session.commit()

    sends: list[str] = []

    class InspectingProvider:
        name = "inspect"

        def send(self, token, title, body, data):
            with SessionLocal() as observer:
                assert observer.get(GameORM, game.id) is not None
                assert observer.scalar(
                    select(func.count()).select_from(NotificationAttemptORM).where(
                        NotificationAttemptORM.status == "pending"
                    )
                ) == 2
            sends.append(token)
            return {"ok": True}

    monkeypatch.setattr(notifications, "get_notification_provider", lambda: InspectingProvider())
    services.create_round_for_game(
        db_session,
        game.id,
        GameRoundCreate(
            prompt="a penguin juggling three umbrellas",
            creator_user_id=creator.id,
        ),
    )

    assert len(sends) == 2
    assert len(notifications.NOTIFICATION_OUTBOX) <= 2
    for index in range(3):
        notifications.notify_user(db_session, creator.id, "Bounded", str(index), {})
    assert [message.body for message in notifications.NOTIFICATION_OUTBOX] == ["1", "2"]


def test_task4_migration_reconciles_duplicate_active_tokens_and_restores_on_downgrade(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "task4-token-migration.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "20260810_0003")

    from sqlalchemy import create_engine

    migrated_engine = create_engine(f"sqlite:///{db_path}")
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, display_name, avatar_emoji, avatar_color, created_at, updated_at) "
                "VALUES ('u1', 'One', '1', '#fff', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
                "('u2', 'Two', '2', '#fff', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO device_tokens "
                "(id, user_id, provider, token, platform, status, created_at, updated_at) VALUES "
                "('old', 'u1', 'expo', 'shared-token', 'ios', 'active', "
                "'2026-01-01 00:00:00', '2026-01-01 00:00:00'), "
                "('new', 'u2', 'expo', 'shared-token', 'android', 'active', "
                "'2026-01-02 00:00:00', '2026-01-02 00:00:00')"
            )
        )

    command.upgrade(config, "head")
    with migrated_engine.connect() as connection:
        active = connection.execute(
            text("SELECT id FROM device_tokens WHERE status = 'active' ORDER BY id")
        ).scalars().all()
        assert active == ["new"]
        assert "registration_id" in {
            column["name"] for column in inspect(migrated_engine).get_columns("device_tokens")
        }
        assert "device_token_retirements" in inspect(migrated_engine).get_table_names()

    command.downgrade(config, "20260810_0003")
    with migrated_engine.connect() as connection:
        active = connection.execute(
            text("SELECT id FROM device_tokens WHERE status = 'active' ORDER BY id")
        ).scalars().all()
        assert active == ["new", "old"]


def test_sqlite_light_migration_does_not_reapply_historical_token_ownership(tmp_path, monkeypatch):
    db_path = tmp_path / "task4-token-light-migration.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "20260810_0003")

    from sqlalchemy import create_engine

    migrated_engine = create_engine(f"sqlite:///{db_path}")
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, display_name, avatar_emoji, avatar_color, created_at, updated_at) "
                "VALUES ('u1', 'One', '1', '#fff', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
                "('u2', 'Two', '2', '#fff', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO device_tokens "
                "(id, user_id, provider, token, platform, status, created_at, updated_at) VALUES "
                "('old', 'u1', 'expo', 'shared-token', 'ios', 'active', "
                "'2026-01-01 00:00:00', '2026-01-01 00:00:00'), "
                "('new', 'u2', 'expo', 'shared-token', 'android', 'active', "
                "'2026-01-02 00:00:00', '2026-01-02 00:00:00')"
            )
        )
    _apply_sqlite_light_migrations(migrated_engine)

    with migrated_engine.begin() as connection:
        connection.execute(text("UPDATE device_tokens SET status = 'inactive' WHERE id = 'new'"))
        connection.execute(
            text(
                "UPDATE device_tokens SET status = 'active', updated_at = '2026-01-03 00:00:00' "
                "WHERE id = 'old'"
            )
        )
    _apply_sqlite_light_migrations(migrated_engine)

    with migrated_engine.connect() as connection:
        active = connection.execute(
            text("SELECT id FROM device_tokens WHERE status = 'active'")
        ).scalars().all()
        assert active == ["old"]


def test_alembic_adopts_task4_objects_created_by_sqlite_startup_compatibility(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "task4-startup-before-alembic.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "20260810_0003")

    from sqlalchemy import create_engine, inspect

    compatibility_engine = create_engine(database_url)
    startup_environment = os.environ.copy()
    startup_environment.update(
        {
            "DATABASE_URL": database_url,
            "AUTO_CREATE_TABLES": "true",
            "ENV": "test",
        }
    )
    subprocess.run(
        [sys.executable, "-c", "from app.db import init_db; init_db()"],
        cwd=Path(__file__).parents[1],
        env=startup_environment,
        check=True,
        capture_output=True,
        text=True,
    )
    before = inspect(compatibility_engine)
    assert "task4_device_token_conflict_archive" in before.get_table_names()
    assert "uq_device_tokens_active_provider_token" in {
        index["name"] for index in before.get_indexes("device_tokens")
    }
    assert "registration_id" in {
        column["name"] for column in before.get_columns("device_tokens")
    }
    assert "device_token_retirements" in before.get_table_names()
    assert "guess_claim_id" in {
        column["name"] for column in before.get_columns("rounds")
    }
    with compatibility_engine.connect() as connection:
        active_round_index_sql = connection.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'uq_rounds_one_active_per_game'")
        ).scalar_one()
    assert "judging" in active_round_index_sql

    command.upgrade(config, "head")

    with compatibility_engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260810_0006"


def test_task4_migration_caps_existing_active_tokens_per_user_and_restores_them(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "task4-token-limit-migration.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "20260810_0003")

    from sqlalchemy import create_engine

    migrated_engine = create_engine(database_url)
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, display_name, avatar_emoji, avatar_color, created_at, updated_at) "
                "VALUES ('owner', 'Owner', '1', '#fff', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        for index in range(5):
            connection.execute(
                text(
                    "INSERT INTO device_tokens "
                    "(id, user_id, provider, token, platform, status, created_at, updated_at) "
                    "VALUES (:id, 'owner', 'expo', :token, 'ios', 'active', :created, :created)"
                ),
                {
                    "id": f"token-{index}",
                    "token": f"unique-token-{index}",
                    "created": f"2026-01-0{index + 1} 00:00:00",
                },
            )

    command.upgrade(config, "head")
    with migrated_engine.connect() as connection:
        active = connection.execute(
            text("SELECT id FROM device_tokens WHERE status = 'active' ORDER BY id")
        ).scalars().all()
        assert active == ["token-2", "token-3", "token-4"]

    command.downgrade(config, "20260810_0003")
    with migrated_engine.connect() as connection:
        active = connection.execute(
            text("SELECT id FROM device_tokens WHERE status = 'active' ORDER BY id")
        ).scalars().all()
        assert active == [f"token-{index}" for index in range(5)]
