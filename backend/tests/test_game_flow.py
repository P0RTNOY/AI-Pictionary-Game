import pytest
from fastapi import HTTPException

from app import services
from app.ai import MockAIProvider
from app.models import DeviceTokenRegister, GameCreate, GameRoundCreate, InviteCreate, InviteJoin, RoundStatus, SvgStatus, UserCreate, UserUpdate
from app.notifications import NOTIFICATION_OUTBOX


@pytest.mark.asyncio
async def test_persistent_multiplayer_round_generation_and_guess(db_session):
    player_1 = services.create_user(db_session, UserCreate(display_name="Omer"))
    player_2 = services.create_user(db_session, UserCreate(display_name="Noa"))
    game = services.create_game(db_session, GameCreate(player_1_id=player_1.id, player_2_id=player_2.id))

    round_record = services.create_round_for_game(
        db_session,
        game.id,
        GameRoundCreate(prompt="a giraffe teaching a dolphin piano", creator_user_id=player_1.id),
    )
    await services.generate_round_svgs(round_record.id)

    generated = services.get_round(db_session, round_record.id)
    assert generated.status == RoundStatus.ready_to_guess
    assert len(generated.generated_svgs) == 3
    assert all(svg.attempts == 1 for svg in generated.generated_svgs)
    assert sum(1 for svg in generated.generated_svgs if svg.status == "done") == 3

    result = services.submit_guess(
        db_session,
        round_record.id,
        "giraffe gives dolphin piano lesson",
        user_id=player_2.id,
    )
    assert result.score >= 50
    assert result.component_scores

    updated_game = services.get_game(db_session, game.id)
    assert updated_game.current_turn_user_id == player_2.id

    events = services.list_events(db_session, game.id)
    event_types = [event.event_type for event in events]
    assert "game.created" in event_types
    assert "round.created" in event_types
    assert "round.ready_to_guess" in event_types
    assert "guess.submitted" in event_types
    assert "turn.changed" in event_types


def test_invalid_turn_and_own_prompt_guess_are_blocked(db_session):
    player_1 = services.create_user(db_session, UserCreate(display_name="Omer"))
    player_2 = services.create_user(db_session, UserCreate(display_name="Noa"))
    game = services.create_game(db_session, GameCreate(player_1_id=player_1.id, player_2_id=player_2.id))

    with pytest.raises(HTTPException) as wrong_turn:
        services.create_round_for_game(
            db_session,
            game.id,
            GameRoundCreate(prompt="a cat eating pizza", creator_user_id=player_2.id),
        )
    assert wrong_turn.value.status_code == 409

    round_record = services.create_round_for_game(
        db_session,
        game.id,
        GameRoundCreate(prompt="a cat eating pizza", creator_user_id=player_1.id),
    )
    stored_round = services.load_round_orm(db_session, round_record.id)
    stored_round.status = RoundStatus.ready_to_guess.value
    db_session.commit()

    with pytest.raises(HTTPException) as own_guess:
        services.submit_guess(db_session, round_record.id, "cat pizza", user_id=player_1.id)
    assert own_guess.value.status_code == 403


def test_duplicate_guess_and_clue_penalty_are_enforced(db_session):
    player_1 = services.create_user(db_session, UserCreate(display_name="Omer"))
    player_2 = services.create_user(db_session, UserCreate(display_name="Noa"))
    game = services.create_game(db_session, GameCreate(player_1_id=player_1.id, player_2_id=player_2.id))
    round_record = services.create_round_for_game(
        db_session,
        game.id,
        GameRoundCreate(prompt="a cat eating pizza on the moon", creator_user_id=player_1.id),
    )
    stored_round = services.load_round_orm(db_session, round_record.id)
    stored_round.status = RoundStatus.ready_to_guess.value
    db_session.commit()

    one_clue_score = services.submit_guess(db_session, round_record.id, "cat eating pizza moon", user_id=player_2.id, clue_count_used=3)
    assert one_clue_score.clue_penalty == 16

    with pytest.raises(HTTPException) as duplicate:
        services.submit_guess(db_session, round_record.id, "cat eating pizza moon", user_id=player_2.id)
    assert duplicate.value.status_code == 409


def test_round_stores_exact_prompt_and_svg_rows_belong_to_round(db_session):
    player_1 = services.create_user(db_session, UserCreate(display_name="Omer"))
    player_2 = services.create_user(db_session, UserCreate(display_name="Noa"))
    game = services.create_game(db_session, GameCreate(player_1_id=player_1.id, player_2_id=player_2.id))
    prompt = "a neon giraffe teaching a dolphin piano inside a tiny submarine"

    round_record = services.create_round_for_game(
        db_session,
        game.id,
        GameRoundCreate(prompt=prompt, creator_user_id=player_1.id),
    )
    stored_round = services.load_round_orm(db_session, round_record.id)

    assert stored_round.original_prompt == prompt
    assert all(svg.round_id == round_record.id for svg in stored_round.generated_svgs)


@pytest.mark.asyncio
async def test_generation_uses_exact_round_prompt_and_retry_reuses_it(db_session, monkeypatch):
    prompts_used = []

    class CapturingProvider:
        name = "capture"

        async def generate_svg(self, challenge, model_config):
            prompts_used.append(challenge)
            return "<svg viewBox='0 0 10 10'><rect x='1' y='1' width='8' height='8'/><circle cx='5' cy='5' r='2'/><path d='M1 9 L9 1'/><line x1='1' y1='1' x2='9' y2='9'/><polygon points='2,8 5,2 8,8'/></svg>"

        async def score_guess(self, original, guess):
            return {}

    monkeypatch.setattr(services, "get_ai_provider", lambda: CapturingProvider())
    player_1 = services.create_user(db_session, UserCreate(display_name="Omer"))
    player_2 = services.create_user(db_session, UserCreate(display_name="Noa"))
    game = services.create_game(db_session, GameCreate(player_1_id=player_1.id, player_2_id=player_2.id))
    prompt = "a robot juggling pancakes on the moon with dramatic lighting"
    round_record = services.create_round_for_game(
        db_session,
        game.id,
        GameRoundCreate(prompt=prompt, creator_user_id=player_1.id),
    )

    await services.generate_round_svgs(round_record.id)
    db_session.expire_all()
    generated = services.get_round(db_session, round_record.id)
    assert generated.status == RoundStatus.ready_to_guess
    assert prompts_used == [prompt, prompt, prompt]

    stored_round = services.load_round_orm(db_session, round_record.id)
    stored_round.generated_svgs[0].status = SvgStatus.failed.value
    stored_round.generated_svgs[0].svg_text = None
    db_session.commit()
    services.prepare_generation_retry(db_session, round_record.id, user_id=player_1.id)
    await services.generate_round_svgs(round_record.id)

    assert prompts_used[-1] == prompt


@pytest.mark.asyncio
async def test_mock_provider_output_reflects_prompt_components():
    svg = await MockAIProvider().generate_svg(
        "a giraffe teaching a dolphin piano on the moon while confused",
        {"tier": "literal"},
    )

    assert "Teaching" in svg
    assert "Giraffe" in svg or "Dolphin" in svg
    assert "Moon" in svg


def test_game_stats_include_round_totals(db_session):
    player_1 = services.create_user(db_session, UserCreate(display_name="Omer"))
    player_2 = services.create_user(db_session, UserCreate(display_name="Noa"))
    game = services.create_game(db_session, GameCreate(player_1_id=player_1.id, player_2_id=player_2.id))
    round_record = services.create_round_for_game(
        db_session,
        game.id,
        GameRoundCreate(prompt="a cat eating pizza on the moon", creator_user_id=player_1.id),
    )
    stored_round = services.load_round_orm(db_session, round_record.id)
    stored_round.status = RoundStatus.ready_to_guess.value
    db_session.commit()

    result = services.submit_guess(db_session, round_record.id, "cat eating pizza moon", user_id=player_2.id)
    stats = services.get_game_stats(db_session, game.id, user_id=player_1.id)

    assert stats.rounds_played == 1
    assert stats.total_score_by_user[player_2.id] == result.score
    assert stats.average_score_by_user[player_2.id] == float(result.score)
    assert stats.best_score == result.score


def test_profile_update_and_access_control(db_session):
    player_1 = services.create_user(db_session, UserCreate(display_name="Omer", avatar_emoji="🟡", avatar_color="#F5C84C"))
    player_2 = services.create_user(db_session, UserCreate(display_name="Noa"))
    stranger = services.create_user(db_session, UserCreate(display_name="Amit"))
    updated = services.update_user(db_session, player_1.id, UserUpdate(display_name="Omer Beta", avatar_color="#24A98C"))
    assert updated.display_name == "Omer Beta"
    assert updated.avatar_color == "#24A98C"

    game = services.create_game(db_session, GameCreate(player_1_id=player_1.id, player_2_id=player_2.id))
    with pytest.raises(HTTPException) as denied:
        services.get_game(db_session, game.id, user_id=stranger.id)
    assert denied.value.status_code == 403


def test_invite_creation_join_and_invalid_joins(db_session):
    creator = services.create_user(db_session, UserCreate(display_name="Omer"))
    opponent = services.create_user(db_session, UserCreate(display_name="Noa"))
    invite = services.create_invite(db_session, InviteCreate(creator_user_id=creator.id))

    with pytest.raises(HTTPException) as own_join:
        services.join_invite(db_session, invite.code, InviteJoin(user_id=creator.id))
    assert own_join.value.status_code == 403

    game = services.join_invite(db_session, invite.code, InviteJoin(user_id=opponent.id))
    assert game.player_1_id == creator.id
    assert game.player_2_id == opponent.id

    with pytest.raises(HTTPException) as second_join:
        services.join_invite(db_session, invite.code, InviteJoin(user_id=opponent.id))
    assert second_join.value.status_code == 409


def test_device_token_and_mock_notifications(db_session):
    NOTIFICATION_OUTBOX.clear()
    player_1 = services.create_user(db_session, UserCreate(display_name="Omer"))
    player_2 = services.create_user(db_session, UserCreate(display_name="Noa"))
    token = services.register_device_token(
        db_session,
        DeviceTokenRegister(
            user_id=player_2.id,
            token="ExponentPushToken[dev-token]",
            platform="ios",
            registration_id="game-flow-device-token",
        ),
    )
    assert token.status == "active"

    game = services.create_game(db_session, GameCreate(player_1_id=player_1.id, player_2_id=player_2.id))
    services.create_round_for_game(
        db_session,
        game.id,
        GameRoundCreate(prompt="a robot making soup", creator_user_id=player_1.id),
    )
    assert any(message.user_id == player_2.id and message.data["type"] == "round.created" for message in NOTIFICATION_OUTBOX)


def test_duplicate_device_token_updates_existing_record(db_session):
    player = services.create_user(db_session, UserCreate(display_name="Omer"))
    first = services.register_device_token(
        db_session,
        DeviceTokenRegister(
            user_id=player.id,
            token="ExponentPushToken[same-device]",
            platform="ios",
            registration_id="duplicate-device-first",
        ),
    )
    second = services.register_device_token(
        db_session,
        DeviceTokenRegister(
            user_id=player.id,
            token="ExponentPushToken[same-device]",
            platform="android",
            registration_id="duplicate-device-second",
        ),
    )

    assert second.id == first.id
    assert second.platform == "android"


def test_debug_test_notification_payload_contains_routing_data(db_session):
    NOTIFICATION_OUTBOX.clear()
    player_1 = services.create_user(db_session, UserCreate(display_name="Omer"))
    player_2 = services.create_user(db_session, UserCreate(display_name="Noa"))
    game = services.create_game(db_session, GameCreate(player_1_id=player_1.id, player_2_id=player_2.id))
    response = services.send_debug_test_notification(db_session, player_1.id, game_id=game.id)

    assert response.queued is True
    assert response.provider == "mock"
    assert NOTIFICATION_OUTBOX[-1].data["type"] == "debug.test"
    assert NOTIFICATION_OUTBOX[-1].data["game_id"] == game.id


def test_prompt_hidden_from_guesser_before_result(db_session):
    player_1 = services.create_user(db_session, UserCreate(display_name="Omer"))
    player_2 = services.create_user(db_session, UserCreate(display_name="Noa"))
    game = services.create_game(db_session, GameCreate(player_1_id=player_1.id, player_2_id=player_2.id))
    round_record = services.create_round_for_game(
        db_session,
        game.id,
        GameRoundCreate(prompt="a secret giraffe piano lesson", creator_user_id=player_1.id),
    )
    as_creator = services.get_game(db_session, game.id, user_id=player_1.id)
    as_guesser = services.get_game(db_session, game.id, user_id=player_2.id)
    assert as_creator.latest_round is not None
    assert as_creator.latest_round.original_prompt == "a secret giraffe piano lesson"
    assert as_guesser.latest_round is not None
    assert as_guesser.latest_round.original_prompt == ""


@pytest.mark.asyncio
async def test_generation_partial_failure_still_readies_round(db_session, monkeypatch):
    class PartialProvider:
        async def generate_svg(self, challenge, model_config):
            if model_config["tier"] == "balanced":
                raise RuntimeError("model unavailable")
            return "<svg viewBox='0 0 10 10'><circle cx='5' cy='5' r='4'/></svg>"

    monkeypatch.setattr(services, "get_ai_provider", lambda: PartialProvider())
    player_1 = services.create_user(db_session, UserCreate(display_name="Omer"))
    player_2 = services.create_user(db_session, UserCreate(display_name="Noa"))
    game = services.create_game(db_session, GameCreate(player_1_id=player_1.id, player_2_id=player_2.id))
    round_record = services.create_round_for_game(
        db_session,
        game.id,
        GameRoundCreate(prompt="a robot juggling pancakes", creator_user_id=player_1.id),
    )

    await services.generate_round_svgs(round_record.id)
    db_session.expire_all()
    generated = services.get_round(db_session, round_record.id)

    assert generated.status == RoundStatus.ready_to_guess
    assert sum(1 for svg in generated.generated_svgs if svg.status == "done") == 2
    assert sum(1 for svg in generated.generated_svgs if svg.status == "failed") == 1


@pytest.mark.asyncio
async def test_generation_retry_skips_ready_sketches(db_session, monkeypatch):
    calls = []

    class RetryProvider:
        async def generate_svg(self, challenge, model_config):
            calls.append(model_config["tier"])
            return f"<svg viewBox='0 0 10 10'><text>{model_config['tier']}</text></svg>"

    monkeypatch.setattr(services, "get_ai_provider", lambda: RetryProvider())
    player_1 = services.create_user(db_session, UserCreate(display_name="Omer"))
    player_2 = services.create_user(db_session, UserCreate(display_name="Noa"))
    game = services.create_game(db_session, GameCreate(player_1_id=player_1.id, player_2_id=player_2.id))
    round_record = services.create_round_for_game(
        db_session,
        game.id,
        GameRoundCreate(prompt="a robot juggling pancakes", creator_user_id=player_1.id),
    )
    stored_round = services.load_round_orm(db_session, round_record.id)
    stored_round.status = RoundStatus.failed.value
    for index, svg in enumerate(stored_round.generated_svgs):
        if index == 0:
            svg.status = SvgStatus.done.value
            svg.svg_text = "<svg viewBox='0 0 10 10'><circle cx='5' cy='5' r='4'/></svg>"
        else:
            svg.status = SvgStatus.failed.value
            svg.error_message = "temporary outage"
    db_session.commit()

    retry_round = services.prepare_generation_retry(db_session, round_record.id, user_id=player_1.id)
    assert retry_round.status == RoundStatus.generating

    await services.generate_round_svgs(round_record.id)
    db_session.expire_all()
    generated = services.get_round(db_session, round_record.id)

    assert generated.status == RoundStatus.ready_to_guess
    assert sum(1 for svg in generated.generated_svgs if svg.status == "done") == 3
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_cross_game_latest_round_selection_regression(db_session, monkeypatch):
    """
    Regression test: Create two games and quickly create rounds in both.
    Ensure that fetching a game's latest round does NOT return the other game's round,
    and generating SVGs uses the exact prompt for that specific game.
    """
    prompts_used = []

    class CapturingProvider:
        name = "capture"
        async def generate_svg(self, challenge, model_config):
            prompts_used.append(challenge)
            return f"<svg viewBox='0 0 10 10'><text>{challenge}</text></svg>"
        async def score_guess(self, original, guess):
            return {}

    monkeypatch.setattr(services, "get_ai_provider", lambda: CapturingProvider())
    
    player_1 = services.create_user(db_session, UserCreate(display_name="Omer"))
    player_2 = services.create_user(db_session, UserCreate(display_name="Noa"))
    
    game_a = services.create_game(db_session, GameCreate(player_1_id=player_1.id, player_2_id=player_2.id))
    game_b = services.create_game(db_session, GameCreate(player_1_id=player_1.id, player_2_id=player_2.id))
    
    prompt_a = "a giraffe teaching a dolphin how to play piano"
    prompt_b = "a jealous cactus juggling inside a courtroom"
    
    # Create rounds almost simultaneously
    round_a = services.create_round_for_game(db_session, game_a.id, GameRoundCreate(prompt=prompt_a, creator_user_id=player_1.id))
    round_b = services.create_round_for_game(db_session, game_b.id, GameRoundCreate(prompt=prompt_b, creator_user_id=player_1.id))
    
    # Generate SVGs
    await services.generate_round_svgs(round_a.id)
    await services.generate_round_svgs(round_b.id)
    
    db_session.expire_all()
    
    # Fetch games
    fetched_game_a = services.get_game(db_session, game_a.id, user_id=player_1.id)
    fetched_game_b = services.get_game(db_session, game_b.id, user_id=player_1.id)
    
    # Verify Game A has Game A's round and prompt
    assert fetched_game_a.latest_round is not None
    assert fetched_game_a.latest_round.id == round_a.id
    assert fetched_game_a.latest_round.game_id == game_a.id
    assert fetched_game_a.latest_round.original_prompt == prompt_a
    assert all(prompt_a in svg.svg_text for svg in fetched_game_a.latest_round.generated_svgs)
    
    # Verify Game B has Game B's round and prompt
    assert fetched_game_b.latest_round is not None
    assert fetched_game_b.latest_round.id == round_b.id
    assert fetched_game_b.latest_round.game_id == game_b.id
    assert fetched_game_b.latest_round.original_prompt == prompt_b
    assert all(prompt_b in svg.svg_text for svg in fetched_game_b.latest_round.generated_svgs)
