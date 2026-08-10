from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import ai, services
from app.main import app, game_events_websocket
from app.models import GameCreate, GameRoundCreate, UserCreate


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def onboard(client: TestClient, name: str) -> tuple[dict, str]:
    response = client.post("/users", json={"display_name": name})
    assert response.status_code == 201
    payload = response.json()
    return payload["user"], payload["access_token"]


def create_joined_game(
    client: TestClient,
    creator: dict,
    creator_token: str,
    joiner: dict,
    joiner_token: str,
) -> dict:
    created = client.post(
        "/invites",
        headers=bearer(creator_token),
        json={"creator_user_id": creator["id"]},
    )
    assert created.status_code == 201
    invite = created.json()

    preview = client.post("/invites/preview", json={"code": invite["code"]})
    assert preview.status_code == 200
    assert set(preview.json()) == {"code", "creator_user_id", "status", "expires_at"}

    joined = client.post(
        "/invites/join",
        headers=bearer(joiner_token),
        json={"code": invite["code"], "user_id": joiner["id"]},
    )
    assert joined.status_code == 201
    return joined.json()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_two_player_http_lifecycle_alternates_turns_and_isolates_games(client):
    artist, artist_token = onboard(client, "Lifecycle Artist")
    guesser, guesser_token = onboard(client, "Lifecycle Guesser")
    outsider, outsider_token = onboard(client, "Other Game Player")
    game = create_joined_game(client, artist, artist_token, guesser, guesser_token)
    other_game = create_joined_game(client, artist, artist_token, outsider, outsider_token)

    wrong_turn = client.post(
        f"/games/{game['id']}/rounds",
        headers=bearer(guesser_token),
        json={"prompt": "a turtle painting a lighthouse", "creator_user_id": guesser["id"]},
    )
    assert wrong_turn.status_code == 409

    first_prompt = "a giraffe teaching a dolphin piano on the moon"
    first_created = client.post(
        f"/games/{game['id']}/rounds",
        headers=bearer(artist_token),
        json={"prompt": first_prompt, "creator_user_id": artist["id"]},
    )
    assert first_created.status_code == 201
    first_round_id = first_created.json()["id"]

    first_for_artist = client.get(f"/rounds/{first_round_id}", headers=bearer(artist_token))
    first_for_guesser = client.get(f"/rounds/{first_round_id}", headers=bearer(guesser_token))
    assert first_for_artist.status_code == first_for_guesser.status_code == 200
    assert first_for_artist.json()["status"] == "ready_to_guess"
    assert first_for_artist.json()["original_prompt"] == first_prompt
    assert first_for_guesser.json()["original_prompt"] == ""
    assert len(first_for_guesser.json()["generated_svgs"]) == 3
    assert {svg["provider_used"] for svg in first_for_guesser.json()["generated_svgs"]} == {"mock"}
    assert all(svg["status"] == "done" and svg["svg_text"] for svg in first_for_guesser.json()["generated_svgs"])

    first_guess = client.post(
        f"/rounds/{first_round_id}/guess",
        headers=bearer(guesser_token),
        json={
            "guess_text": "giraffe teaching dolphin piano moon",
            "user_id": guesser["id"],
            "clue_count_used": 2,
        },
    )
    assert first_guess.status_code == 200
    assert 0 <= first_guess.json()["score"] <= 100
    assert first_guess.json()["component_scores"]

    first_result = client.get(f"/rounds/{first_round_id}", headers=bearer(guesser_token))
    assert first_result.json()["status"] == "guessed"
    assert first_result.json()["original_prompt"] == first_prompt
    assert first_result.json()["guess"]["round_id"] == first_round_id
    assert client.get(f"/games/{game['id']}", headers=bearer(artist_token)).json()["current_turn_user_id"] == guesser["id"]

    second_prompt = "a robot juggling pancakes inside a castle"
    second_created = client.post(
        f"/games/{game['id']}/rounds",
        headers=bearer(guesser_token),
        json={"prompt": second_prompt, "creator_user_id": guesser["id"]},
    )
    assert second_created.status_code == 201
    second_round_id = second_created.json()["id"]
    second_waiting = client.get(f"/rounds/{second_round_id}", headers=bearer(artist_token))
    assert second_waiting.status_code == 200
    assert second_waiting.json()["original_prompt"] == ""

    second_guess = client.post(
        f"/rounds/{second_round_id}/guess",
        headers=bearer(artist_token),
        json={"guess_text": "robot juggling pancakes castle", "user_id": artist["id"]},
    )
    assert second_guess.status_code == 200

    stats = client.get(f"/games/{game['id']}/stats", headers=bearer(artist_token))
    assert stats.status_code == 200
    assert stats.json()["rounds_played"] == 2
    assert stats.json()["total_score_by_user"][artist["id"]] == second_guess.json()["score"]
    assert stats.json()["total_score_by_user"][guesser["id"]] == first_guess.json()["score"]
    assert stats.json()["current_turn_user_id"] == artist["id"]

    game_events = client.get(f"/games/{game['id']}/events", headers=bearer(guesser_token))
    assert game_events.status_code == 200
    assert all(event["game_id"] == game["id"] for event in game_events.json())
    assert first_prompt not in json.dumps(game_events.json())
    assert second_prompt not in json.dumps(game_events.json())
    assert {event["event_type"] for event in game_events.json()} >= {
        "game.created",
        "round.created",
        "round.ready_to_guess",
        "guess.submitted",
        "round.scored",
        "turn.changed",
    }

    assert client.get(f"/games/{other_game['id']}", headers=bearer(guesser_token)).status_code == 403
    other_events = client.get(f"/games/{other_game['id']}/events", headers=bearer(outsider_token))
    assert other_events.status_code == 200
    assert all(event["game_id"] == other_game["id"] for event in other_events.json())
    assert {event["id"] for event in game_events.json()}.isdisjoint(
        {event["id"] for event in other_events.json()}
    )


def test_websocket_replay_and_polling_keep_per_game_cursors_isolated(client, db_session):
    shared, shared_token = onboard(client, "Shared Player")
    first_peer, first_peer_token = onboard(client, "First Peer")
    second_peer, second_peer_token = onboard(client, "Second Peer")
    first_game = create_joined_game(client, shared, shared_token, first_peer, first_peer_token)
    second_game = create_joined_game(client, shared, shared_token, second_peer, second_peer_token)

    services.add_event(db_session, first_game["id"], "qa.first.initial", {"marker": "first-initial"})
    services.add_event(db_session, second_game["id"], "qa.second.initial", {"marker": "second-initial"})
    db_session.commit()

    first_initial = client.get(
        f"/games/{first_game['id']}/events?after_id=0",
        headers=bearer(first_peer_token),
    )
    second_initial = client.get(
        f"/games/{second_game['id']}/events?after_id=0",
        headers=bearer(second_peer_token),
    )
    assert first_initial.status_code == second_initial.status_code == 200
    assert all(event["game_id"] == first_game["id"] for event in first_initial.json())
    assert all(event["game_id"] == second_game["id"] for event in second_initial.json())
    assert "second-initial" not in json.dumps(first_initial.json())
    assert "first-initial" not in json.dumps(second_initial.json())
    first_cursor = first_initial.json()[-1]["id"]
    second_cursor = second_initial.json()[-1]["id"]

    services.add_event(db_session, second_game["id"], "qa.second.reconnect", {"marker": "second-reconnect"})
    services.add_event(db_session, first_game["id"], "qa.first.reconnect", {"marker": "first-reconnect"})
    db_session.commit()

    first_poll = client.get(
        f"/games/{first_game['id']}/events?after_id={first_cursor}",
        headers=bearer(first_peer_token),
    )
    second_poll = client.get(
        f"/games/{second_game['id']}/events?after_id={second_cursor}",
        headers=bearer(second_peer_token),
    )
    assert [event["event_type"] for event in first_poll.json()] == ["qa.first.reconnect"]
    assert [event["event_type"] for event in second_poll.json()] == ["qa.second.reconnect"]

    first_ticket = client.post(
        f"/games/{first_game['id']}/websocket-ticket",
        headers=bearer(first_peer_token),
    )
    assert first_ticket.status_code == 201
    with client.websocket_connect(
        f"/ws/games/{first_game['id']}?ticket={first_ticket.json()['ticket']}&after_id={first_cursor}"
    ) as websocket:
        connected = websocket.receive_json()
        replayed = websocket.receive_json()
        assert connected == {"type": "connected", "game_id": first_game["id"], "after_id": first_cursor}
        assert replayed["type"] == "event"
        assert replayed["event"]["event_type"] == "qa.first.reconnect"
        assert replayed["event"]["game_id"] == first_game["id"]

    with pytest.raises(WebSocketDisconnect) as replay_rejected:
        with client.websocket_connect(
            f"/ws/games/{first_game['id']}?ticket={first_ticket.json()['ticket']}&after_id={first_cursor}"
        ):
            pass
    assert getattr(replay_rejected.value, "code", None) == 1008

    second_ticket = client.post(
        f"/games/{second_game['id']}/websocket-ticket",
        headers=bearer(second_peer_token),
    )
    assert second_ticket.status_code == 201
    with client.websocket_connect(
        f"/ws/games/{second_game['id']}?ticket={second_ticket.json()['ticket']}&after_id={second_cursor}"
    ) as websocket:
        assert websocket.receive_json()["type"] == "connected"
        replayed = websocket.receive_json()
        assert replayed["event"]["event_type"] == "qa.second.reconnect"
        assert replayed["event"]["game_id"] == second_game["id"]


@pytest.mark.asyncio
async def test_idle_websocket_observes_client_disconnect_without_waiting_for_an_event(monkeypatch):
    class EmptySession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    class DisconnectingWebSocket:
        query_params = {"ticket": "single-use-ticket", "after_id": "0"}

        def __init__(self):
            self.accepted = False
            self.sent = []
            self.receive_calls = 0
            self.cancelled_receives = 0
            self.active_receive_tasks = 0
            self.close_calls = 0

        async def accept(self):
            self.accepted = True

        async def send_json(self, payload):
            self.sent.append(payload)

        async def receive(self):
            self.receive_calls += 1
            receive_number = self.receive_calls
            self.active_receive_tasks += 1
            try:
                if receive_number == 1:
                    try:
                        await asyncio.Future()
                    except asyncio.CancelledError:
                        self.cancelled_receives += 1
                        raise
                return {"type": "websocket.disconnect", "code": 1000}
            finally:
                self.active_receive_tasks -= 1

        async def close(self, code):
            self.close_calls += 1

    websocket = DisconnectingWebSocket()
    event_polls = 0

    def list_no_events(db, game_id, after_id, user_id):
        nonlocal event_polls
        event_polls += 1
        return []

    monkeypatch.setattr(services, "SessionLocal", EmptySession)
    monkeypatch.setattr(services, "consume_websocket_ticket", lambda db, ticket, game_id: "player-id")
    monkeypatch.setattr(services, "list_events", list_no_events)

    await asyncio.wait_for(game_events_websocket(websocket, "game-id"), timeout=2.0)

    assert websocket.accepted is True
    assert event_polls == 2
    assert websocket.receive_calls == 2
    assert websocket.cancelled_receives == 1
    assert websocket.active_receive_tasks == 0
    assert websocket.close_calls == 0
    assert websocket.sent == [
        {"type": "connected", "game_id": "game-id", "after_id": 0}
    ]


def test_uvicorn_websocket_handshake_logs_redact_single_use_ticket():
    raw_ticket = "single-use-ticket-must-not-enter-logs"
    record = logging.LogRecord(
        name="uvicorn.error",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "WebSocket %s" [accepted]',
        args=(("127.0.0.1", 12345), f"/ws/games/game-id?ticket={raw_ticket}&after_id=7"),
        exc_info=None,
    )

    for installed_filter in logging.getLogger("uvicorn.error").filters:
        assert installed_filter.filter(record) is True
    rendered = record.getMessage()
    assert raw_ticket not in rendered
    assert "ticket=%5BREDACTED%5D" in rendered
    assert "after_id=7" in rendered


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_mode", ["malformed", "oversized", "timeout", "http_error", "unavailable"])
async def test_local_provider_failures_end_in_stable_retryable_round_state(
    db_session,
    monkeypatch,
    failure_mode,
):
    real_async_client = httpx.AsyncClient

    async def handler(request: httpx.Request) -> httpx.Response:
        if failure_mode == "malformed":
            return httpx.Response(200, content=b"not-json")
        if failure_mode == "oversized":
            return httpx.Response(
                200,
                headers={"Content-Length": str(ai.DEFAULT_PROVIDER_RESPONSE_MAX_BYTES + 1)},
                content=b"{}",
            )
        if failure_mode == "timeout":
            raise httpx.ReadTimeout("provider timed out with private detail", request=request)
        if failure_mode == "http_error":
            return httpx.Response(503, json={"private": "upstream detail"})
        raise httpx.ConnectError("local provider unavailable with private detail", request=request)

    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", "https://local-model.invalid")
    monkeypatch.setenv("LOCAL_MODEL_NAME", "qa-local-model")
    monkeypatch.setattr(
        ai.httpx,
        "AsyncClient",
        lambda **kwargs: real_async_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    creator = services.create_user(db_session, UserCreate(display_name=f"Creator {failure_mode}"))
    guesser = services.create_user(db_session, UserCreate(display_name=f"Guesser {failure_mode}"))
    game = services.create_game(
        db_session,
        GameCreate(player_1_id=creator.id, player_2_id=guesser.id),
    )
    round_record = services.create_round_for_game(
        db_session,
        game.id,
        GameRoundCreate(
            prompt="a private narwhal repairing a bicycle",
            creator_user_id=creator.id,
        ),
    )

    await services.generate_round_svgs(round_record.id)

    db_session.expire_all()
    failed = services.get_round(db_session, round_record.id)
    assert failed.status == "failed"
    assert all(svg.status == "failed" for svg in failed.generated_svgs)
    assert all(svg.provider_used == "local" for svg in failed.generated_svgs)
    assert all(svg.attempts == 1 for svg in failed.generated_svgs)
    assert {svg.error_message for svg in failed.generated_svgs} == {
        services.PUBLIC_GENERATION_ERROR_MESSAGE
    }
    event_dump = json.dumps(
        [event.model_dump() for event in services.list_events(db_session, game.id)]
    )
    assert "private detail" not in event_dump
    assert "upstream detail" not in event_dump


def test_missing_local_provider_configuration_does_not_block_startup_and_retry_recovers(
    monkeypatch,
):
    startup_entered = False
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def observed_lifespan(application):
        nonlocal startup_entered
        async with original_lifespan(application) as state:
            startup_entered = True
            yield state

    monkeypatch.setattr(app.router, "lifespan_context", observed_lifespan)
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.delenv("LOCAL_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("LOCAL_MODEL_NAME", raising=False)

    with TestClient(app) as client:
        assert startup_entered is True
        assert client.get("/health").json() == {"status": "ok"}
        status = client.get("/ai/status")
        assert status.status_code == 200
        assert status.json()["runtime_provider"] == "local"
        assert status.json()["local_model_configured"] is False

        creator, creator_token = onboard(client, "Retry Creator")
        guesser, guesser_token = onboard(client, "Retry Guesser")
        game = create_joined_game(client, creator, creator_token, guesser, guesser_token)
        created = client.post(
            f"/games/{game['id']}/rounds",
            headers=bearer(creator_token),
            json={"prompt": "a fox building a radio", "creator_user_id": creator["id"]},
        )
        assert created.status_code == 201
        round_id = created.json()["id"]
        failed = client.get(f"/rounds/{round_id}", headers=bearer(creator_token))
        assert failed.json()["status"] == "failed"
        assert {svg["provider_used"] for svg in failed.json()["generated_svgs"]} == {None}

        monkeypatch.setenv("AI_PROVIDER", "mock")
        retried = client.post(
            f"/rounds/{round_id}/retry-generation",
            headers=bearer(creator_token),
            json={"user_id": creator["id"]},
        )
        assert retried.status_code == 200
        recovered = client.get(f"/rounds/{round_id}", headers=bearer(creator_token))
        assert recovered.json()["status"] == "ready_to_guess"
        assert {svg["provider_used"] for svg in recovered.json()["generated_svgs"]} == {"mock"}
        assert all(svg["attempts"] == 2 for svg in recovered.json()["generated_svgs"])
    assert startup_entered is True


def test_in_process_alembic_upgrade_preserves_existing_application_loggers(tmp_path, monkeypatch):
    database_path = tmp_path / "logger-isolation.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    application_logger = logging.getLogger("ai_pictionary.services")
    original_disabled = application_logger.disabled
    application_logger.disabled = False

    try:
        command.upgrade(config, "head")
        assert application_logger.disabled is False
    finally:
        application_logger.disabled = original_disabled
