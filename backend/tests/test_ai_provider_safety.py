from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from app import ai, services
from app.db import _apply_sqlite_light_migrations
from app.main import app
from app.models import GameCreate, GameRoundCreate, RoundStatus, SvgStatus, UserCreate


PUBLIC_GENERATION_ERROR_CODE = "generation_failed"
PUBLIC_GENERATION_ERROR_MESSAGE = "Drawing generation failed. Please try again."


def create_test_round(db_session, prompt: str = "a robot juggling pancakes on the moon"):
    player_1 = services.create_user(db_session, UserCreate(display_name="Artist"))
    player_2 = services.create_user(db_session, UserCreate(display_name="Guesser"))
    game = services.create_game(db_session, GameCreate(player_1_id=player_1.id, player_2_id=player_2.id))
    round_record = services.create_round_for_game(
        db_session,
        game.id,
        GameRoundCreate(prompt=prompt, creator_user_id=player_1.id),
    )
    return player_1, game, round_record


class SuccessfulProvider:
    def __init__(self, name: str):
        self.name = name

    async def generate_svg(self, challenge, model_config):
        return "<svg viewBox='0 0 10 10'><circle cx='5' cy='5' r='4'/></svg>"


@pytest.mark.asyncio
async def test_generation_persists_provenance_from_actual_provider(db_session, monkeypatch):
    _, _, round_record = create_test_round(db_session)
    assert all(svg.provider_used is None for svg in round_record.generated_svgs)
    monkeypatch.setattr(services, "get_ai_provider", lambda: SuccessfulProvider("actual-provider"))

    await services.generate_round_svgs(round_record.id)

    db_session.expire_all()
    generated = services.get_round(db_session, round_record.id)
    assert {svg.provider_used for svg in generated.generated_svgs} == {"actual-provider"}


@pytest.mark.asyncio
async def test_retry_replaces_provenance_only_for_retried_sketches(db_session, monkeypatch):
    player, _, round_record = create_test_round(db_session)
    active_provider = SuccessfulProvider("first-provider")
    monkeypatch.setattr(services, "get_ai_provider", lambda: active_provider)
    await services.generate_round_svgs(round_record.id)

    stored = services.load_round_orm(db_session, round_record.id)
    retried_id = stored.generated_svgs[1].id
    stored.generated_svgs[1].status = SvgStatus.failed.value
    stored.generated_svgs[1].svg_text = None
    db_session.commit()
    services.prepare_generation_retry(db_session, round_record.id, player.id)

    active_provider = SuccessfulProvider("retry-provider")
    await services.generate_round_svgs(round_record.id)

    db_session.expire_all()
    generated = services.get_round(db_session, round_record.id)
    provenance = {svg.id: svg.provider_used for svg in generated.generated_svgs}
    assert provenance[retried_id] == "retry-provider"
    assert {provider for svg_id, provider in provenance.items() if svg_id != retried_id} == {"first-provider"}


def test_unknown_provider_raises_stable_configuration_error(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "not-a-provider")

    with pytest.raises(ai.AIConfigurationError, match="^Unsupported AI provider configuration$"):
        ai.get_ai_provider()


@pytest.mark.asyncio
async def test_provider_constructor_failure_finalizes_round_for_retry(db_session, monkeypatch):
    _, game, round_record = create_test_round(db_session)

    def fail_to_construct():
        raise RuntimeError("credential secret-value was rejected")

    monkeypatch.setattr(services, "get_ai_provider", fail_to_construct)
    await services.generate_round_svgs(round_record.id)

    db_session.expire_all()
    generated = services.get_round(db_session, round_record.id)
    assert generated.status == RoundStatus.failed
    assert all(svg.status == SvgStatus.failed for svg in generated.generated_svgs)
    assert all(svg.attempts == 1 for svg in generated.generated_svgs)
    assert all(svg.provider_used is None for svg in generated.generated_svgs)
    assert {svg.error_message for svg in generated.generated_svgs} == {PUBLIC_GENERATION_ERROR_MESSAGE}
    failure = [event for event in services.list_events(db_session, game.id) if event.event_type == "round.failed"][-1]
    assert failure.payload["code"] == PUBLIC_GENERATION_ERROR_CODE
    assert failure.payload["message"] == PUBLIC_GENERATION_ERROR_MESSAGE
    assert "secret-value" not in json.dumps(failure.payload)


@pytest.mark.asyncio
async def test_provider_constructor_failure_preserves_partial_retry_success(db_session, monkeypatch):
    player, game, round_record = create_test_round(db_session)
    monkeypatch.setattr(services, "get_ai_provider", lambda: SuccessfulProvider("first-provider"))
    await services.generate_round_svgs(round_record.id)

    stored = services.load_round_orm(db_session, round_record.id)
    completed = stored.generated_svgs[0]
    completed_snapshot = {
        "id": completed.id,
        "provider_used": completed.provider_used,
        "svg_text": completed.svg_text,
        "attempts": completed.attempts,
    }
    retryable_ids = {svg.id for svg in stored.generated_svgs[1:]}
    for svg in stored.generated_svgs[1:]:
        svg.status = SvgStatus.failed.value
        svg.svg_text = None
        svg.error_message = "old public error"
    db_session.commit()
    services.prepare_generation_retry(db_session, round_record.id, player.id)

    def fail_to_construct():
        raise RuntimeError("credential secret-value was rejected")

    monkeypatch.setattr(services, "get_ai_provider", fail_to_construct)
    await services.generate_round_svgs(round_record.id)

    db_session.expire_all()
    generated = services.get_round(db_session, round_record.id)
    completed_after = next(svg for svg in generated.generated_svgs if svg.id == completed_snapshot["id"])
    retryable_after = [svg for svg in generated.generated_svgs if svg.id in retryable_ids]
    assert generated.status == RoundStatus.ready_to_guess
    assert completed_after.status == SvgStatus.done
    assert completed_after.provider_used == completed_snapshot["provider_used"] == "first-provider"
    assert completed_after.svg_text == completed_snapshot["svg_text"]
    assert completed_after.attempts == completed_snapshot["attempts"] == 1
    assert all(svg.status == SvgStatus.failed for svg in retryable_after)
    assert all(svg.attempts == 2 for svg in retryable_after)
    assert all(svg.provider_used is None for svg in retryable_after)
    assert {svg.error_message for svg in retryable_after} == {PUBLIC_GENERATION_ERROR_MESSAGE}

    terminal_events = [
        event
        for event in services.list_events(db_session, game.id)
        if event.event_type in {"round.ready_to_guess", "round.failed"}
    ]
    assert terminal_events[-1].event_type == "round.ready_to_guess"
    assert terminal_events[-1].payload["available_svgs"] == 1
    assert terminal_events[-1].payload["code"] == PUBLIC_GENERATION_ERROR_CODE
    assert terminal_events[-1].payload["message"] == PUBLIC_GENERATION_ERROR_MESSAGE
    assert "secret-value" not in json.dumps(terminal_events[-1].payload)


@pytest.mark.asyncio
async def test_provider_failures_redact_prompts_and_exception_details(db_session, monkeypatch, caplog):
    prompt = "a private narwhal password dancing in a vault"

    class FailingProvider:
        name = "safe-provider-name"

        async def generate_svg(self, challenge, model_config):
            raise RuntimeError("upstream body with token=secret-value")

    caplog.set_level(logging.INFO)
    _, game, round_record = create_test_round(db_session, prompt=prompt)
    monkeypatch.setattr(services, "get_ai_provider", FailingProvider)
    await services.generate_round_svgs(round_record.id)

    db_session.expire_all()
    generated = services.get_round(db_session, round_record.id)
    assert {svg.error_message for svg in generated.generated_svgs} == {PUBLIC_GENERATION_ERROR_MESSAGE}
    failures = [event for event in services.list_events(db_session, game.id) if event.event_type == "svg.failed"]
    assert failures
    assert all(event.payload["code"] == PUBLIC_GENERATION_ERROR_CODE for event in failures)
    public_data = json.dumps([event.payload for event in failures])
    assert "secret-value" not in public_data
    assert "upstream body" not in public_data
    assert prompt not in caplog.text
    assert "secret-value" not in caplog.text
    assert any(
        getattr(record, "exception_type", "").endswith(".RuntimeError")
        for record in caplog.records
        if record.getMessage() == "generation.svg_failed"
    )


class ChunkedStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


@pytest.mark.asyncio
async def test_bounded_json_rejects_oversized_declared_response():
    async def handler(request):
        return httpx.Response(200, headers={"Content-Length": "101"}, content=b"{}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ai.ProviderResponseError, match="^Provider response exceeded the configured size limit$"):
            await ai.request_json_bounded(client, "POST", "https://provider.invalid", max_bytes=100)


@pytest.mark.asyncio
async def test_bounded_json_rejects_oversized_streamed_response():
    async def handler(request):
        return httpx.Response(200, stream=ChunkedStream([b'{"value":"', b"x" * 100, b'"}']))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ai.ProviderResponseError, match="^Provider response exceeded the configured size limit$"):
            await ai.request_json_bounded(client, "POST", "https://provider.invalid", max_bytes=100)


@pytest.mark.asyncio
async def test_local_provider_rejects_malformed_response_shape(monkeypatch):
    real_async_client = httpx.AsyncClient

    async def handler(request):
        return httpx.Response(200, json={"choices": []})

    transport = httpx.MockTransport(handler)
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", "https://local-model.invalid")
    monkeypatch.setenv("LOCAL_MODEL_NAME", "test-model")
    monkeypatch.setattr(ai.httpx, "AsyncClient", lambda **kwargs: real_async_client(transport=transport, **kwargs))

    with pytest.raises(ai.ProviderResponseError, match="^Provider response had an invalid shape$"):
        await ai.LocalModelProvider().generate_svg("a robot dancing", {"tier": "literal"})


def test_ai_status_schema_includes_complete_local_configuration(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", "https://local-model.invalid")
    monkeypatch.setenv("LOCAL_MODEL_NAME", "configured-model")

    response = TestClient(app).get("/ai/status")

    assert response.status_code == 200
    assert response.json()["runtime_provider"] == "local"
    assert response.json()["local_model_configured"] is True
    assert "LOCAL_MODEL_BASE_URL" not in response.text
    assert "configured-model" not in response.text


def test_sqlite_light_migration_adds_nullable_provider_used(tmp_path):
    database_path = tmp_path / "legacy.db"
    disposable_engine = create_engine(f"sqlite:///{database_path}")
    with disposable_engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE generated_svgs ("
                "id VARCHAR(64) PRIMARY KEY, model_tier VARCHAR(40) NOT NULL"
                ")"
            )
        )

    _apply_sqlite_light_migrations(disposable_engine)

    columns = {column["name"]: column for column in inspect(disposable_engine).get_columns("generated_svgs")}
    assert "provider_used" in columns
    assert columns["provider_used"]["nullable"] is True


def test_provider_used_alembic_migration_is_nullable_and_reversible(tmp_path, monkeypatch):
    database_path = tmp_path / "alembic-provider.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))

    command.upgrade(config, "20260701_0001")
    initial_engine = create_engine(f"sqlite:///{database_path}")
    assert "provider_used" not in {column["name"] for column in inspect(initial_engine).get_columns("generated_svgs")}

    command.upgrade(config, "head")
    upgraded = {column["name"]: column for column in inspect(initial_engine).get_columns("generated_svgs")}
    assert upgraded["provider_used"]["nullable"] is True

    command.downgrade(config, "20260701_0001")
    downgraded = {column["name"] for column in inspect(initial_engine).get_columns("generated_svgs")}
    assert "provider_used" not in downgraded
