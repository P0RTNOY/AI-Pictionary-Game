from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime, timedelta, timezone
from threading import Event

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, inspect, select, text
from sqlalchemy.orm import sessionmaker
from starlette.websockets import WebSocketDisconnect

from app import services
from app.db import SessionLocal, _apply_sqlite_light_migrations, get_db
from app.main import app
from app.models import GameCreate, InviteCreate
from app.orm_models import GameInvite as GameInviteORM
from app.orm_models import WebSocketTicket as WebSocketTicketORM


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


def test_websocket_ticket_is_hashed_scoped_single_use_and_never_logged(client, db_session, caplog):
    creator, creator_token = onboard(client, "Ticket Creator")
    guesser, _ = onboard(client, "Ticket Guesser")
    _, stranger_token = onboard(client, "Ticket Stranger")
    game = services.create_game(
        db_session,
        GameCreate(player_1_id=creator["id"], player_2_id=guesser["id"]),
    )

    assert client.post(
        f"/games/{game.id}/websocket-ticket", headers=bearer(stranger_token)
    ).status_code == 403

    issued = client.post(f"/games/{game.id}/websocket-ticket", headers=bearer(creator_token))
    assert issued.status_code == 201
    ticket = issued.json()["ticket"]
    assert len(ticket) >= 32
    stored = db_session.execute(
        text("SELECT ticket_hash FROM websocket_tickets WHERE game_id = :game_id"),
        {"game_id": game.id},
    ).scalar_one()
    assert stored == hashlib.sha256(ticket.encode()).hexdigest()
    assert stored != ticket

    caplog.set_level(logging.INFO)
    with client.websocket_connect(f"/ws/games/{game.id}?ticket={ticket}") as websocket:
        assert websocket.receive_json()["type"] == "connected"
    with pytest.raises(WebSocketDisconnect) as reused:
        with client.websocket_connect(f"/ws/games/{game.id}?ticket={ticket}"):
            pass
    assert reused.value.code == 1008

    rejected_ticket = "rejected-ticket-must-never-be-logged"
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/games/{game.id}?ticket={rejected_ticket}"):
            pass
    assert ticket not in caplog.text
    assert rejected_ticket not in caplog.text


def test_invite_capabilities_use_fixed_post_targets_and_never_appear_in_logs(client, caplog, monkeypatch):
    creator, creator_token = onboard(client, "Invite Creator")
    joiner, joiner_token = onboard(client, "Invite Joiner")
    created = client.post("/invites", headers=bearer(creator_token), json={})
    assert created.status_code == 201
    code = created.json()["code"]
    assert 22 <= len(code) <= 24

    caplog.set_level(logging.INFO)
    preview = client.post("/invites/preview", json={"code": code})
    assert preview.status_code == 200
    assert preview.request.url.path == "/invites/preview"
    joined = client.post(
        "/invites/join",
        headers=bearer(joiner_token),
        json={"code": code, "user_id": joiner["id"]},
    )
    assert joined.status_code == 201
    assert joined.request.url.path == "/invites/join"
    assert code not in caplog.text

    monkeypatch.setattr("app.main.ENV", "staging")
    monkeypatch.setattr("app.main.DEBUG", True)
    assert client.get(f"/invites/{code}", headers=bearer(creator_token)).status_code == 404


def test_fixed_invite_endpoints_accept_legacy_six_character_codes_exactly(client, db_session):
    creator, _ = onboard(client, "Legacy Code Creator")
    joiner, joiner_token = onboard(client, "Legacy Code Joiner")
    code = "Ab_9-x"
    db_session.add(
        GameInviteORM(
            code=code,
            creator_user_id=creator["id"],
            status="pending",
            expires_at=services.now() + timedelta(days=1),
        )
    )
    db_session.commit()

    preview = client.post("/invites/preview", json={"code": code})
    assert preview.status_code == 200
    assert preview.json()["code"] == code
    joined = client.post("/invites/join", headers=bearer(joiner_token), json={"code": code})
    assert joined.status_code == 201
    assert joined.json()["player_2_id"] == joiner["id"]


def test_websocket_ticket_has_exactly_one_winner_under_concurrent_consumption(client, db_session):
    creator, creator_token = onboard(client, "Concurrent Ticket Creator")
    guesser, _ = onboard(client, "Concurrent Ticket Guesser")
    game = services.create_game(db_session, GameCreate(player_1_id=creator["id"], player_2_id=guesser["id"]))
    issued = client.post(f"/games/{game.id}/websocket-ticket", headers=bearer(creator_token))
    assert issued.status_code == 201
    raw_ticket = issued.json()["ticket"]
    db_session.close()

    def consume() -> str:
        with SessionLocal() as concurrent_db:
            try:
                return services.consume_websocket_ticket(concurrent_db, raw_ticket, game.id)
            except Exception as exc:  # noqa: BLE001 - compare the public authentication outcome
                return f"error:{getattr(exc, 'status_code', None)}"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: consume(), range(2)))
    assert results.count(creator["id"]) == 1
    assert results.count("error:401") == 1


def test_websocket_ticket_rotation_wins_against_paused_old_ticket_consumption(client, db_session):
    creator, creator_token = onboard(client, "CAS Ticket Creator")
    guesser, _ = onboard(client, "CAS Ticket Guesser")
    game = services.create_game(db_session, GameCreate(player_1_id=creator["id"], player_2_id=guesser["id"]))
    old_response = client.post(
        f"/games/{game.id}/websocket-ticket",
        headers=bearer(creator_token),
    )
    assert old_response.status_code == 201
    old_ticket = old_response.json()["ticket"]
    db_session.close()

    old_ticket_selected = Event()
    rotation_committed = Event()

    def consume_paused_old_ticket() -> str:
        with SessionLocal() as consuming_db:
            original_scalar = consuming_db.scalar

            def synchronized_scalar(statement, *args, **kwargs):
                result = original_scalar(statement, *args, **kwargs)
                if isinstance(result, WebSocketTicketORM):
                    old_ticket_selected.set()
                    assert rotation_committed.wait(timeout=5)
                return result

            consuming_db.scalar = synchronized_scalar  # type: ignore[method-assign]
            try:
                return services.consume_websocket_ticket(consuming_db, old_ticket, game.id)
            except Exception as exc:  # noqa: BLE001 - assert the generic authentication result
                return f"error:{getattr(exc, 'status_code', None)}"

    with ThreadPoolExecutor(max_workers=1) as pool:
        old_consumer = pool.submit(consume_paused_old_ticket)
        assert old_ticket_selected.wait(timeout=5)
        try:
            with SessionLocal() as issuing_db:
                new_ticket = services.issue_websocket_ticket(issuing_db, game.id, creator["id"]).ticket
        finally:
            rotation_committed.set()
        old_outcome = old_consumer.result(timeout=5)

    assert old_outcome == "error:401"
    with SessionLocal() as verification_db:
        assert services.consume_websocket_ticket(verification_db, new_ticket, game.id) == creator["id"]


def test_websocket_ticket_rotation_cleanup_indexes_and_concurrent_issuance_are_bounded(client, db_session):
    creator, creator_token = onboard(client, "Bounded Ticket Creator")
    guesser, _ = onboard(client, "Bounded Ticket Guesser")
    game = services.create_game(db_session, GameCreate(player_1_id=creator["id"], player_2_id=guesser["id"]))
    endpoint = f"/games/{game.id}/websocket-ticket"

    first = client.post(endpoint, headers=bearer(creator_token)).json()["ticket"]
    second = client.post(endpoint, headers=bearer(creator_token)).json()["ticket"]
    assert db_session.scalar(select(WebSocketTicketORM).where(WebSocketTicketORM.game_id == game.id)) is not None
    assert db_session.query(WebSocketTicketORM).filter_by(user_id=creator["id"], game_id=game.id).count() == 1
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/games/{game.id}?ticket={first}"):
            pass
    with client.websocket_connect(f"/ws/games/{game.id}?ticket={second}") as websocket:
        assert websocket.receive_json()["type"] == "connected"

    third = client.post(endpoint, headers=bearer(creator_token)).json()["ticket"]
    assert db_session.query(WebSocketTicketORM).count() == 1
    stored = db_session.scalar(select(WebSocketTicketORM))
    stored.expires_at = services.now() - timedelta(seconds=1)
    db_session.commit()
    fourth = client.post(endpoint, headers=bearer(creator_token)).json()["ticket"]
    assert fourth != third
    assert db_session.query(WebSocketTicketORM).count() == 1

    db_session.execute(delete(WebSocketTicketORM))
    db_session.commit()

    db_session.close()

    def issue() -> str:
        with SessionLocal() as concurrent_db:
            try:
                return services.issue_websocket_ticket(concurrent_db, game.id, creator["id"]).ticket
            except Exception as exc:  # noqa: BLE001 - verify bounded outcome under a real race
                return f"error:{getattr(exc, 'status_code', None)}"

    with ThreadPoolExecutor(max_workers=2) as pool:
        issued = list(pool.map(lambda _: issue(), range(2)))
    with SessionLocal() as verification_db:
        assert verification_db.query(WebSocketTicketORM).filter_by(
            user_id=creator["id"], game_id=game.id, consumed_at=None
        ).count() == 1
        indexes = {index["name"]: index for index in inspect(verification_db.bind).get_indexes("websocket_tickets")}
        assert {
            "ix_websocket_tickets_expires_at",
            "ix_websocket_tickets_consumed_at",
            "uq_websocket_tickets_user_game",
        } <= indexes.keys()
        assert indexes["uq_websocket_tickets_user_game"]["unique"] == 1

    valid = 0
    for raw_ticket in issued:
        if raw_ticket.startswith("error:"):
            continue
        with SessionLocal() as consume_db:
            try:
                services.consume_websocket_ticket(consume_db, raw_ticket, game.id)
                valid += 1
            except Exception:
                pass
    assert valid == 1

    with SessionLocal() as repeated_db:
        for _ in range(20):
            services.issue_websocket_ticket(repeated_db, game.id, guesser["id"])
        assert repeated_db.query(WebSocketTicketORM).count() <= 2


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("get", "/debug/health/full", None),
        ("get", "/debug/events", None),
        ("get", "/debug/games", None),
        ("get", "/debug/notification-outbox", None),
        ("post", "/debug/send-test-notification", {"user_id": "forged"}),
    ],
)
def test_every_debug_route_requires_bearer(client, method, path, payload):
    response = getattr(client, method)(path, json=payload) if payload is not None else getattr(client, method)(path)
    assert response.status_code == 401


def test_debug_routes_are_local_only_and_send_as_authenticated_actor(client, monkeypatch):
    actor, token = onboard(client, "Debug Actor")
    forged, _ = onboard(client, "Forged Target")
    headers = bearer(token)
    local_send = client.post(
        "/debug/send-test-notification",
        headers=headers,
        json={"user_id": forged["id"]},
    )
    assert local_send.status_code == 403

    monkeypatch.setattr("app.main.ENV", "staging")
    monkeypatch.setattr("app.main.DEBUG", True)
    for path in ("/debug/health/full", "/debug/events", "/debug/games", "/debug/notification-outbox"):
        assert client.get(path, headers=headers).status_code == 404
    assert actor["id"] != forged["id"]


def test_debug_reset_api_is_not_exposed_even_in_local_debug(client):
    _, token = onboard(client, "No Reset Actor")
    assert client.post("/debug/reset-local-data", headers=bearer(token)).status_code == 404


def test_debug_reset_service_is_not_part_of_task3():
    assert not hasattr(services, "reset_local_database")


def test_server_command_disables_default_access_log():
    dockerfile = Path(__file__).parents[1] / "Dockerfile"
    assert "--no-access-log" in dockerfile.read_text()


def test_upgrade_reconciles_and_archives_legacy_conflicts_then_downgrade_restores_them(tmp_path):
    backend_dir = Path(__file__).parents[1]
    database_path = tmp_path / "legacy.sqlite3"
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "3ada93e0ae67")

    migration_engine = create_engine(f"sqlite:///{database_path}")
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with migration_engine.begin() as connection:
        for user_id in ("u1", "u2"):
            connection.execute(
                text(
                    "INSERT INTO users (id, display_name, avatar_emoji, avatar_color, created_at, updated_at) "
                    "VALUES (:id, :name, '🙂', '#F5C84C', :created, :updated)"
                ),
                {"id": user_id, "name": user_id, "created": timestamp, "updated": timestamp},
            )
        connection.execute(
            text(
                "INSERT INTO games (id, player_1_id, player_2_id, current_turn_user_id, status, created_at, updated_at) "
                "VALUES ('g1', 'u1', 'u2', 'u1', 'active', :created, :updated)"
            ),
            {"created": timestamp, "updated": timestamp},
        )
        connection.execute(
            text(
                "INSERT INTO games (id, player_1_id, player_2_id, current_turn_user_id, status, created_at, updated_at) "
                "VALUES ('g2', 'u1', 'u2', 'u1', 'active', :created, :updated)"
            ),
            {"created": timestamp, "updated": timestamp},
        )
        for offset, (round_id, status) in enumerate((("r1", "generating"), ("r2", "ready_to_guess"))):
            round_timestamp = timestamp + timedelta(days=offset)
            connection.execute(
                text(
                    "INSERT INTO rounds (id, game_id, creator_user_id, guesser_user_id, original_prompt, status, "
                    "clue_reveal_count, created_at, updated_at) "
                    "VALUES (:id, 'g1', 'u1', 'u2', 'legacy prompt', :status, 1, :created, :updated)"
                ),
                {"id": round_id, "status": status, "created": round_timestamp, "updated": round_timestamp},
            )
        for round_id in ("tie-a", "tie-b"):
            connection.execute(
                text(
                    "INSERT INTO rounds (id, game_id, creator_user_id, guesser_user_id, original_prompt, status, "
                    "clue_reveal_count, created_at, updated_at) "
                    "VALUES (:id, 'g2', 'u1', 'u2', 'tie prompt', 'generating', 1, :created, :updated)"
                ),
                {"id": round_id, "created": timestamp, "updated": timestamp},
            )
        for guess_id, score in (("guess-a", 10), ("guess-b", 20)):
            connection.execute(
                text(
                    "INSERT INTO guesses (id, round_id, user_id, guess_text, score, judge_result_json, "
                    "component_scores_json, clue_count_used, created_at, updated_at) "
                    "VALUES (:id, 'r1', 'u2', 'legacy guess', :score, '{}', '{}', 1, :created, :updated)"
                ),
                {"id": guess_id, "score": score, "created": timestamp, "updated": timestamp},
            )
        connection.execute(
            text(
                "INSERT INTO game_invites (code, creator_user_id, status, expires_at, created_at, updated_at) "
                "VALUES ('Ab_9-x', 'u1', 'pending', :expires, :created, :updated)"
            ),
            {
                "expires": datetime(2030, 1, 1, tzinfo=timezone.utc),
                "created": timestamp,
                "updated": timestamp,
            },
        )

    command.upgrade(config, "head")
    with migration_engine.begin() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM guesses WHERE round_id = 'r1'")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM task3_guess_conflict_archive")).scalar_one() == 1
        active = connection.execute(
            text("SELECT COUNT(*) FROM rounds WHERE game_id = 'g1' AND status IN ('generating', 'ready_to_guess')")
        ).scalar_one()
        assert active == 1
        assert connection.execute(text("SELECT COUNT(*) FROM task3_active_round_archive")).scalar_one() == 2
        assert connection.execute(text("SELECT status FROM rounds WHERE id = 'tie-b'")).scalar_one() == "generating"
        assert connection.execute(text("SELECT status FROM rounds WHERE id = 'tie-a'")).scalar_one() == "failed"
        connection.execute(
            text("UPDATE users SET session_token_hash = :token_hash WHERE id = 'u1'"),
            {"token_hash": services.hash_access_token("legacy-view-token")},
        )

    MigrationSession = sessionmaker(bind=migration_engine, expire_on_commit=False)

    def migration_db_override():
        with MigrationSession() as migration_db:
            yield migration_db

    app.dependency_overrides[get_db] = migration_db_override
    try:
        with TestClient(app) as migration_client:
            game_view = migration_client.get("/games/g1", headers=bearer("legacy-view-token"))
            assert game_view.status_code == 200
            assert game_view.json()["latest_round"]["id"] == "r2"
            assert game_view.json()["latest_round"]["status"] == "ready_to_guess"

            preview = migration_client.post("/invites/preview", json={"code": "Ab_9-x"})
            assert preview.status_code == 200
            assert preview.json()["code"] == "Ab_9-x"
            joiner_session = migration_client.post("/users", json={"display_name": "Legacy Joiner"}).json()
            joined = migration_client.post(
                "/invites/join",
                headers=bearer(joiner_session["access_token"]),
                json={"code": "Ab_9-x"},
            )
            assert joined.status_code == 201
    finally:
        app.dependency_overrides.pop(get_db, None)

    with MigrationSession() as migration_db:
        invite = services.create_invite(migration_db, InviteCreate(creator_user_id="u1"))
        assert 22 <= len(invite.code) <= 24

    command.downgrade(config, "3ada93e0ae67")
    with migration_engine.begin() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM guesses WHERE round_id = 'r1'")).scalar_one() == 2
        statuses = connection.execute(text("SELECT status FROM rounds WHERE game_id = 'g1' ORDER BY id")).scalars().all()
        assert statuses == ["generating", "ready_to_guess"]
        assert connection.execute(text("SELECT COUNT(*) FROM game_invites WHERE code = 'Ab_9-x'")).scalar_one() == 1
        assert "websocket_tickets" not in inspect(migration_engine).get_table_names()
        connection.execute(
            text(
                "CREATE TABLE websocket_tickets ("
                "id VARCHAR(64) PRIMARY KEY, ticket_hash VARCHAR(64) NOT NULL, "
                "user_id VARCHAR(64) NOT NULL, game_id VARCHAR(64) NOT NULL, "
                "expires_at DATETIME NOT NULL, consumed_at DATETIME, created_at DATETIME NOT NULL)"
            )
        )
        for ticket_id in ("legacy-ticket-a", "legacy-ticket-b"):
            connection.execute(
                text(
                    "INSERT INTO websocket_tickets "
                    "(id, ticket_hash, user_id, game_id, expires_at, created_at) "
                    "VALUES (:id, :ticket_hash, 'u1', 'g1', :expires_at, :created_at)"
                ),
                {
                    "id": ticket_id,
                    "ticket_hash": hashlib.sha256(ticket_id.encode()).hexdigest(),
                    "expires_at": datetime(2030, 1, 1, tzinfo=timezone.utc),
                    "created_at": timestamp,
                },
            )

    _apply_sqlite_light_migrations(bind=migration_engine)
    with migration_engine.begin() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM guesses WHERE round_id = 'r1'")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM task3_guess_conflict_archive")).scalar_one() == 1
        assert connection.execute(
            text("SELECT COUNT(*) FROM rounds WHERE game_id = 'g1' AND status IN ('generating', 'ready_to_guess')")
        ).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM task3_active_round_archive")).scalar_one() == 2
        assert connection.execute(text("SELECT status FROM rounds WHERE id = 'r2'")).scalar_one() == "ready_to_guess"
        assert connection.execute(text("SELECT COUNT(*) FROM websocket_tickets")).scalar_one() == 1
        ticket_indexes = {index["name"] for index in inspect(migration_engine).get_indexes("websocket_tickets")}
        assert "uq_websocket_tickets_user_game" in ticket_indexes
