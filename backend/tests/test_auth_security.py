from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from starlette.websockets import WebSocketDisconnect

from app import services
from app.db import SessionLocal
from app.main import app
from app.models import GameCreate, GameRoundCreate, InviteCreate, InviteJoin, RoundStatus, UserCreate
from app.orm_models import Game as GameORM
from app.orm_models import GameEvent as GameEventORM
from app.orm_models import Guess as GuessORM
from app.orm_models import Round as RoundORM
from app.orm_models import User as UserORM
from app.notifications import NOTIFICATION_OUTBOX


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reset_invite_attempts():
    reset = getattr(services, "reset_invite_attempt_limiter", None)
    if reset:
        reset()
    yield
    if reset:
        reset()


def onboard(client: TestClient, name: str) -> tuple[dict, str]:
    response = client.post("/users", json={"display_name": name})
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"user", "access_token", "token_type"}
    return body["user"], body["access_token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_service_user(db, name: str):
    return services.create_user(db, UserCreate(display_name=name))


def create_service_game(db, first_name: str = "First", second_name: str = "Second"):
    first = create_service_user(db, first_name)
    second = create_service_user(db, second_name)
    game = services.create_game(db, GameCreate(player_1_id=first.id, player_2_id=second.id))
    return first, second, game


def test_onboarding_returns_one_time_opaque_session_and_stores_only_its_hash(client, db_session):
    response = client.post(
        "/users",
        json={
            "display_name": "Beta Player",
            "auth_provider": "forged-provider",
            "auth_subject": "forged-subject",
        },
    )

    assert response.status_code == 422

    response = client.post("/users", json={"display_name": "Beta Player"})
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"user", "access_token", "token_type"}
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) >= 43
    assert "session_token_hash" not in body["user"]

    stored = db_session.get(UserORM, body["user"]["id"])
    assert stored is not None
    assert stored.session_token_hash == hashlib.sha256(body["access_token"].encode()).hexdigest()
    assert stored.session_token_hash != body["access_token"]
    assert stored.auth_provider is None
    assert stored.auth_subject is None


@pytest.mark.parametrize(
    "method,path,json_body",
    [
        ("get", "/users/does-not-matter", None),
        ("get", "/users/does-not-matter/games", None),
        ("get", "/games/does-not-matter", None),
        ("get", "/games/does-not-matter/stats", None),
        ("get", "/games/does-not-matter/events", None),
        ("get", "/rounds/does-not-matter", None),
        ("post", "/invites", {"creator_user_id": "forged"}),
        (
            "post",
            "/device-tokens",
            {
                "user_id": "forged",
                "token": "ExponentPushToken[forged]",
                "registration_id": "missing-bearer-registration",
            },
        ),
    ],
)
def test_private_http_routes_reject_missing_bearer_with_uniform_challenge(client, method, path, json_body):
    request = getattr(client, method)
    response = request(path, json=json_body) if json_body is not None else request(path)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Invalid or missing bearer token"}


def test_invalid_bearer_uses_the_same_generic_401(client):
    response = client.get("/users/not-a-user", headers=bearer("not-a-real-token"))

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Invalid or missing bearer token"}


def test_verified_actor_owns_profile_and_game_listing(client):
    owner, owner_token = onboard(client, "Owner")
    victim, _ = onboard(client, "Victim")

    assert client.get(f"/users/{owner['id']}", headers=bearer(owner_token)).status_code == 200
    assert client.get(f"/users/{victim['id']}", headers=bearer(owner_token)).status_code == 403
    assert client.patch(
        f"/users/{victim['id']}", headers=bearer(owner_token), json={"display_name": "Stolen"}
    ).status_code == 403
    assert client.get(f"/users/{victim['id']}/games", headers=bearer(owner_token)).status_code == 403


def test_participant_only_reads_and_prompt_visibility_use_verified_actor(client, db_session):
    creator, creator_token = onboard(client, "Creator")
    guesser, guesser_token = onboard(client, "Guesser")
    _, stranger_token = onboard(client, "Stranger")
    game = services.create_game(db_session, GameCreate(player_1_id=creator["id"], player_2_id=guesser["id"]))
    round_record = services.create_round_for_game(
        db_session,
        game.id,
        GameRoundCreate(prompt="a hidden giraffe conducting an orchestra", creator_user_id=creator["id"]),
    )

    creator_game = client.get(f"/games/{game.id}", headers=bearer(creator_token))
    guesser_game = client.get(f"/games/{game.id}", headers=bearer(guesser_token))
    assert creator_game.status_code == 200
    assert creator_game.json()["latest_round"]["original_prompt"] == "a hidden giraffe conducting an orchestra"
    assert guesser_game.status_code == 200
    assert guesser_game.json()["latest_round"]["original_prompt"] == ""

    for path in (
        f"/games/{game.id}",
        f"/games/{game.id}/stats",
        f"/games/{game.id}/events",
        f"/rounds/{round_record.id}",
    ):
        assert client.get(path, headers=bearer(stranger_token)).status_code == 403

    guesser_round = client.get(f"/rounds/{round_record.id}", headers=bearer(guesser_token))
    assert guesser_round.status_code == 200
    assert guesser_round.json()["original_prompt"] == ""


def test_forged_actor_fields_cannot_authorize_mutations(client, db_session):
    creator, creator_token = onboard(client, "Creator")
    guesser, guesser_token = onboard(client, "Guesser")
    stranger, stranger_token = onboard(client, "Stranger")
    game = services.create_game(db_session, GameCreate(player_1_id=creator["id"], player_2_id=guesser["id"]))
    round_record = services.create_round_for_game(
        db_session,
        game.id,
        GameRoundCreate(prompt="a walrus painting a tiny castle", creator_user_id=creator["id"]),
    )
    stored_round = services.load_round_orm(db_session, round_record.id)
    stored_round.status = RoundStatus.failed.value
    db_session.commit()

    forged_round = client.post(
        f"/games/{game.id}/rounds",
        headers=bearer(stranger_token),
        json={"prompt": "a forged challenge prompt", "creator_user_id": creator["id"]},
    )
    assert forged_round.status_code == 403

    forged_retry = client.post(
        f"/rounds/{round_record.id}/retry-generation",
        headers=bearer(stranger_token),
        json={"user_id": creator["id"]},
    )
    assert forged_retry.status_code == 403

    stored_round.status = RoundStatus.ready_to_guess.value
    db_session.commit()
    forged_guess = client.post(
        f"/rounds/{round_record.id}/guess",
        headers=bearer(stranger_token),
        json={"user_id": guesser["id"], "guess_text": "walrus castle", "clue_count_used": 1},
    )
    assert forged_guess.status_code == 403

    forged_invite = client.post(
        "/invites",
        headers=bearer(stranger_token),
        json={"creator_user_id": creator["id"]},
    )
    assert forged_invite.status_code == 403

    invite = services.create_invite(db_session, InviteCreate(creator_user_id=creator["id"]))
    forged_join = client.post(
        "/invites/join",
        headers=bearer(stranger_token),
        json={"code": invite.code, "user_id": guesser["id"]},
    )
    assert forged_join.status_code == 403

    forged_token = client.post(
        "/device-tokens",
        headers=bearer(stranger_token),
        json={
            "user_id": creator["id"],
            "token": "ExponentPushToken[attacker]",
            "platform": "ios",
            "registration_id": "forged-token-registration",
        },
    )
    assert forged_token.status_code == 403

    own_token = client.post(
        "/device-tokens",
        headers=bearer(creator_token),
        json={
            "user_id": creator["id"],
            "token": "ExponentPushToken[creator]",
            "platform": "ios",
            "registration_id": "creator-token-registration",
        },
    )
    assert own_token.status_code == 201


def test_retry_is_creator_only_and_guess_is_guesser_only(client, db_session):
    creator, creator_token = onboard(client, "Creator")
    guesser, guesser_token = onboard(client, "Guesser")
    game = services.create_game(db_session, GameCreate(player_1_id=creator["id"], player_2_id=guesser["id"]))
    round_record = services.create_round_for_game(
        db_session,
        game.id,
        GameRoundCreate(prompt="a jellyfish repairing a bicycle", creator_user_id=creator["id"]),
    )
    stored_round = services.load_round_orm(db_session, round_record.id)
    stored_round.status = RoundStatus.failed.value
    db_session.commit()

    denied_retry = client.post(
        f"/rounds/{round_record.id}/retry-generation",
        headers=bearer(guesser_token),
        json={},
    )
    assert denied_retry.status_code == 403

    stored_round.status = RoundStatus.ready_to_guess.value
    db_session.commit()
    denied_guess = client.post(
        f"/rounds/{round_record.id}/guess",
        headers=bearer(creator_token),
        json={"guess_text": "jellyfish bicycle", "clue_count_used": 1},
    )
    assert denied_guess.status_code == 403


def test_websocket_rejects_missing_invalid_and_nonparticipant_tickets_before_accept(client, db_session):
    creator, creator_token = onboard(client, "Creator")
    guesser, _ = onboard(client, "Guesser")
    _, stranger_token = onboard(client, "Stranger")
    game = services.create_game(db_session, GameCreate(player_1_id=creator["id"], player_2_id=guesser["id"]))

    for query in ("", "?ticket=invalid"):
        with pytest.raises(WebSocketDisconnect) as rejected:
            with client.websocket_connect(f"/ws/games/{game.id}{query}"):
                pass
        assert rejected.value.code == 1008

    assert client.post(f"/games/{game.id}/websocket-ticket", headers=bearer(stranger_token)).status_code == 403
    ticket_response = client.post(f"/games/{game.id}/websocket-ticket", headers=bearer(creator_token))
    assert ticket_response.status_code == 201
    with client.websocket_connect(f"/ws/games/{game.id}?ticket={ticket_response.json()['ticket']}") as websocket:
        assert websocket.receive_json()["type"] == "connected"


def test_direct_game_and_legacy_round_creation_are_unreachable_outside_local_debug(client, monkeypatch):
    first, first_token = onboard(client, "First")
    second, _ = onboard(client, "Second")
    monkeypatch.setattr("app.main.ENV", "staging")
    monkeypatch.setattr("app.main.DEBUG", True)

    direct_game = client.post(
        "/games",
        headers=bearer(first_token),
        json={"player_1_id": first["id"], "player_2_id": second["id"]},
    )
    legacy_round = client.post(
        "/rounds",
        headers=bearer(first_token),
        json={
            "prompt": "a legacy bypass challenge",
            "creator_user_id": first["id"],
            "guesser_user_id": second["id"],
        },
    )

    assert direct_game.status_code == 404
    assert legacy_round.status_code == 404


def test_invite_preview_is_minimal_and_code_has_high_entropy(client):
    creator, creator_token = onboard(client, "Creator")
    created = client.post(
        "/invites",
        headers=bearer(creator_token),
        json={"creator_user_id": creator["id"]},
    )
    assert created.status_code == 201
    full_invite = created.json()
    assert len(full_invite["code"]) >= 22

    preview = client.post("/invites/preview", json={"code": full_invite["code"]})
    assert preview.status_code == 200
    assert set(preview.json()) == {"code", "creator_user_id", "status", "expires_at"}


def test_invite_lookup_and_join_attempts_share_a_source_bound(monkeypatch, client):
    monkeypatch.setattr(services, "INVITE_ATTEMPT_LIMIT", 2, raising=False)
    monkeypatch.setattr(services, "INVITE_ATTEMPT_WINDOW_SECONDS", 60, raising=False)
    reset = getattr(services, "reset_invite_attempt_limiter", None)
    if reset:
        reset()

    assert client.post("/invites/preview", json={"code": "missing-one-code"}).status_code == 404
    assert client.post(
        "/invites/preview", json={"code": "missing-two-code"}, headers={"X-Forwarded-For": "203.0.113.9"}
    ).status_code == 404
    limited = client.post(
        "/invites/preview", json={"code": "missing-three-code"}, headers={"X-Forwarded-For": "198.51.100.7"}
    )

    assert limited.status_code == 429
    assert limited.json() == {"detail": {"code": "invite_rate_limited", "message": "Too many invite attempts"}}


def test_invite_attempt_limiter_caps_tracked_source_state(monkeypatch):
    monkeypatch.setattr(services, "INVITE_RATE_LIMIT_MAX_SOURCES", 1)
    services.check_invite_attempt("source-one", timestamp=100.0)

    with pytest.raises(Exception) as limited:
        services.check_invite_attempt("source-two", timestamp=100.0)

    assert getattr(limited.value, "status_code", None) == 429


def test_invite_pending_to_accepted_consumption_is_atomic(db_session, monkeypatch):
    creator = create_service_user(db_session, "Creator")
    joiner_a = create_service_user(db_session, "Joiner A")
    joiner_b = create_service_user(db_session, "Joiner B")
    invite = services.create_invite(db_session, InviteCreate(creator_user_id=creator.id))
    db_session.close()

    barrier = Barrier(2)
    original_refresh = services.refresh_invite_expiry

    def synchronize_after_load(db, loaded_invite):
        original_refresh(db, loaded_invite)
        barrier.wait(timeout=5)

    monkeypatch.setattr(services, "refresh_invite_expiry", synchronize_after_load)

    def join(user_id: str):
        with SessionLocal() as concurrent_db:
            try:
                game = services.join_invite(concurrent_db, invite.code, InviteJoin(user_id=user_id))
                return ("ok", game.id)
            except Exception as exc:  # noqa: BLE001 - the assertion checks the externally relevant outcome
                return ("error", getattr(exc, "status_code", None) or repr(exc))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(join, (joiner_a.id, joiner_b.id)))

    assert sorted(status for status, _ in results) == ["error", "ok"], results
    assert [value for status, value in results if status == "error"] == [409]
    with SessionLocal() as verification_db:
        game_count = verification_db.scalar(select(func.count()).select_from(GameORM))
    assert game_count == 1


def test_concurrent_round_creation_has_one_transition_and_one_notification(db_session, monkeypatch):
    NOTIFICATION_OUTBOX.clear()
    creator, guesser, game = create_service_game(db_session, "Creator", "Guesser")
    game_id = game.id
    creator_id = creator.id
    db_session.close()
    barrier = Barrier(2)
    original_enforce = services.enforce_new_round_budgets

    def synchronize_before_admission(db, user_id):
        barrier.wait(timeout=5)
        return original_enforce(db, user_id)

    monkeypatch.setattr(services, "enforce_new_round_budgets", synchronize_before_admission)

    def create(prompt: str):
        with SessionLocal() as concurrent_db:
            try:
                round_record = services.create_round_for_game(
                    concurrent_db,
                    game_id,
                    GameRoundCreate(prompt=prompt, creator_user_id=creator_id),
                )
                return ("ok", round_record.id)
            except Exception as exc:  # noqa: BLE001 - verify one externally visible conflict
                return ("error", getattr(exc, "status_code", None) or repr(exc))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, ("a fox painting a lighthouse", "a bear painting a lighthouse")))

    assert sorted(status for status, _ in results) == ["error", "ok"], results
    assert [value for status, value in results if status == "error"] == [409]
    with SessionLocal() as verification_db:
        assert verification_db.scalar(select(func.count()).select_from(RoundORM)) == 1
        round_created_events = verification_db.scalar(
            select(func.count()).select_from(GameEventORM).where(GameEventORM.event_type == "round.created")
        )
    assert round_created_events == 1
    assert sum(message.user_id == guesser.id for message in NOTIFICATION_OUTBOX) == 1


def test_concurrent_guess_submission_has_one_transition_and_one_notification_pair(db_session, monkeypatch):
    NOTIFICATION_OUTBOX.clear()
    creator, guesser, game = create_service_game(db_session, "Creator", "Guesser")
    round_record = services.create_round_for_game(
        db_session,
        game.id,
        GameRoundCreate(prompt="a fox painting a lighthouse", creator_user_id=creator.id),
    )
    stored_round = services.load_round_orm(db_session, round_record.id)
    stored_round.status = RoundStatus.ready_to_guess.value
    db_session.commit()
    NOTIFICATION_OUTBOX.clear()
    round_id = round_record.id
    guesser_id = guesser.id
    db_session.close()
    barrier = Barrier(2)
    original_load = services.load_round_orm

    def synchronize_after_load(db, requested_round_id):
        loaded = original_load(db, requested_round_id)
        barrier.wait(timeout=5)
        return loaded

    monkeypatch.setattr(services, "load_round_orm", synchronize_after_load)

    def guess(text_value: str):
        with SessionLocal() as concurrent_db:
            try:
                result = services.submit_guess(concurrent_db, round_id, text_value, user_id=guesser_id)
                return ("ok", result.score)
            except Exception as exc:  # noqa: BLE001 - verify one externally visible conflict
                return ("error", getattr(exc, "status_code", None) or repr(exc))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(guess, ("fox lighthouse", "painting lighthouse")))

    assert sorted(status for status, _ in results) == ["error", "ok"], results
    assert [value for status, value in results if status == "error"] == [409]
    with SessionLocal() as verification_db:
        assert verification_db.scalar(select(func.count()).select_from(GuessORM)) == 1
        guess_events = verification_db.scalar(
            select(func.count()).select_from(GameEventORM).where(GameEventORM.event_type == "guess.submitted")
        )
    assert guess_events == 1
    assert len(NOTIFICATION_OUTBOX) == 2


def test_per_user_daily_round_budget_is_database_backed(db_session, monkeypatch):
    monkeypatch.setattr(services, "PER_USER_DAILY_ROUND_LIMIT", 1, raising=False)
    monkeypatch.setattr(services, "GLOBAL_DAILY_ROUND_LIMIT", 10, raising=False)
    monkeypatch.setattr(services, "GLOBAL_GENERATING_ROUND_LIMIT", 10, raising=False)
    creator = create_service_user(db_session, "Creator")
    opponent_a = create_service_user(db_session, "Opponent A")
    opponent_b = create_service_user(db_session, "Opponent B")
    game_a = services.create_game(db_session, GameCreate(player_1_id=creator.id, player_2_id=opponent_a.id))
    game_b = services.create_game(db_session, GameCreate(player_1_id=creator.id, player_2_id=opponent_b.id))

    first = services.create_round_for_game(
        db_session, game_a.id, GameRoundCreate(prompt="a penguin baking bread", creator_user_id=creator.id)
    )
    services.load_round_orm(db_session, first.id).status = RoundStatus.failed.value
    db_session.commit()

    with pytest.raises(Exception) as limited:
        services.create_round_for_game(
            db_session, game_b.id, GameRoundCreate(prompt="a turtle reading maps", creator_user_id=creator.id)
        )
    assert getattr(limited.value, "status_code", None) == 429
    assert limited.value.detail["code"] == "user_daily_round_limit"


def test_global_daily_round_budget_is_database_backed(db_session, monkeypatch):
    monkeypatch.setattr(services, "PER_USER_DAILY_ROUND_LIMIT", 10, raising=False)
    monkeypatch.setattr(services, "GLOBAL_DAILY_ROUND_LIMIT", 1, raising=False)
    monkeypatch.setattr(services, "GLOBAL_GENERATING_ROUND_LIMIT", 10, raising=False)
    first, second, game_a = create_service_game(db_session, "First", "Second")
    third, fourth, game_b = create_service_game(db_session, "Third", "Fourth")

    round_a = services.create_round_for_game(
        db_session, game_a.id, GameRoundCreate(prompt="a penguin baking bread", creator_user_id=first.id)
    )
    services.load_round_orm(db_session, round_a.id).status = RoundStatus.failed.value
    db_session.commit()

    with pytest.raises(Exception) as limited:
        services.create_round_for_game(
            db_session, game_b.id, GameRoundCreate(prompt="a turtle reading maps", creator_user_id=third.id)
        )
    assert getattr(limited.value, "status_code", None) == 429
    assert limited.value.detail["code"] == "global_daily_round_limit"


def test_global_generating_ceiling_applies_to_new_rounds_and_retries(db_session, monkeypatch):
    monkeypatch.setattr(services, "PER_USER_DAILY_ROUND_LIMIT", 10, raising=False)
    monkeypatch.setattr(services, "GLOBAL_DAILY_ROUND_LIMIT", 10, raising=False)
    monkeypatch.setattr(services, "GLOBAL_GENERATING_ROUND_LIMIT", 1, raising=False)
    first, _, game_a = create_service_game(db_session, "First", "Second")
    third, _, game_b = create_service_game(db_session, "Third", "Fourth")
    fifth, _, game_c = create_service_game(db_session, "Fifth", "Sixth")

    target = services.create_round_for_game(
        db_session,
        game_c.id,
        GameRoundCreate(prompt="a retryable turtle reading maps", creator_user_id=fifth.id),
    )
    stored_target = services.load_round_orm(db_session, target.id)
    stored_target.status = RoundStatus.failed.value
    for svg in stored_target.generated_svgs:
        svg.status = "failed"
    db_session.commit()
    active = services.create_round_for_game(
        db_session, game_a.id, GameRoundCreate(prompt="a penguin baking bread", creator_user_id=first.id)
    )

    with pytest.raises(Exception) as new_limited:
        services.create_round_for_game(
            db_session, game_b.id, GameRoundCreate(prompt="a fox building a radio", creator_user_id=third.id)
        )
    assert getattr(new_limited.value, "status_code", None) == 503
    assert new_limited.value.detail["code"] == "generation_capacity_reached"

    with pytest.raises(Exception) as retry_limited:
        services.prepare_generation_retry(db_session, target.id, fifth.id)
    assert getattr(retry_limited.value, "status_code", None) == 503
    assert retry_limited.value.detail["code"] == "generation_capacity_reached"
    assert services.load_round_orm(db_session, active.id).status == RoundStatus.generating.value


def test_database_metadata_enforces_one_guess_and_one_active_round(db_session):
    first, second, game = create_service_game(db_session)
    round_record = RoundORM(
        id=services.new_id(),
        game_id=game.id,
        creator_user_id=first.id,
        guesser_user_id=second.id,
        original_prompt="a metadata constraint prompt",
        status=RoundStatus.failed.value,
    )
    db_session.add(round_record)
    db_session.commit()

    guesses = [
        GuessORM(
            id=services.new_id(),
            round_id=round_record.id,
            user_id=second.id,
            guess_text="first guess",
            score=50,
            judge_result_json="{}",
            component_scores_json="{}",
            clue_count_used=1,
        ),
        GuessORM(
            id=services.new_id(),
            round_id=round_record.id,
            user_id=second.id,
            guess_text="second guess",
            score=60,
            judge_result_json="{}",
            component_scores_json="{}",
            clue_count_used=1,
        ),
    ]
    db_session.add_all(guesses)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    active_rounds = [
        RoundORM(
            id=services.new_id(),
            game_id=game.id,
            creator_user_id=first.id,
            guesser_user_id=second.id,
            original_prompt="one active prompt",
            status=RoundStatus.generating.value,
        ),
        RoundORM(
            id=services.new_id(),
            game_id=game.id,
            creator_user_id=first.id,
            guesser_user_id=second.id,
            original_prompt="another active prompt",
            status=RoundStatus.ready_to_guess.value,
        ),
    ]
    db_session.add_all(active_rounds)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_metadata_exposes_required_auth_and_integrity_indexes():
    user_indexes = {index.name: index for index in UserORM.__table__.indexes}
    guess_indexes = {index.name: index for index in GuessORM.__table__.indexes}
    round_indexes = {index.name: index for index in RoundORM.__table__.indexes}

    assert "session_token_hash" in UserORM.__table__.columns
    assert user_indexes["ix_users_session_token_hash"].unique is True
    assert guess_indexes["uq_guesses_round_id"].unique is True
    assert round_indexes["uq_rounds_one_active_per_game"].unique is True


def test_auth_migration_preserves_legacy_users_and_round_trips_sqlite(tmp_path, monkeypatch):
    database_path = tmp_path / "auth_migration.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "3ada93e0ae67")

    migration_engine = create_engine(database_url)
    with migration_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users "
                "(id, display_name, avatar_emoji, avatar_color, created_at, updated_at) "
                "VALUES ('legacy-user', 'Legacy User', '🙂', '#F5C84C', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )

    command.upgrade(config, "head")
    upgraded = inspect(migration_engine)
    assert "session_token_hash" in {column["name"] for column in upgraded.get_columns("users")}
    assert {index["name"] for index in upgraded.get_indexes("users")} >= {"ix_users_session_token_hash"}
    assert {index["name"] for index in upgraded.get_indexes("guesses")} >= {"uq_guesses_round_id"}
    assert {index["name"] for index in upgraded.get_indexes("rounds")} >= {"uq_rounds_one_active_per_game"}
    assert "generation_admission_gate" in upgraded.get_table_names()
    with migration_engine.connect() as connection:
        assert connection.scalar(
            text("SELECT session_token_hash FROM users WHERE id = 'legacy-user'")
        ) is None

    command.downgrade(config, "3ada93e0ae67")
    downgraded = inspect(migration_engine)
    assert "session_token_hash" not in {column["name"] for column in downgraded.get_columns("users")}
    assert "generation_admission_gate" not in downgraded.get_table_names()
    command.downgrade(config, "base")
    migration_engine.dispose()
