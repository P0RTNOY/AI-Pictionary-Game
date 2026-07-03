"""initial schema

Revision ID: 20260701_0001
Revises:
Create Date: 2026-07-01
"""

from alembic import op
import sqlalchemy as sa


revision = "20260701_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("avatar_url", sa.String(500)),
        sa.Column("avatar_emoji", sa.String(16), nullable=False, server_default="🙂"),
        sa.Column("avatar_color", sa.String(16), nullable=False, server_default="#F5C84C"),
        sa.Column("auth_provider", sa.String(40)),
        sa.Column("auth_subject", sa.String(160)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "games",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("player_1_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("player_2_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("current_turn_user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "game_invites",
        sa.Column("code", sa.String(24), primary_key=True),
        sa.Column("creator_user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("game_id", sa.String(64), sa.ForeignKey("games.id")),
        sa.Column("status", sa.String(40), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_by_user_id", sa.String(64), sa.ForeignKey("users.id")),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "device_tokens",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False, server_default="expo"),
        sa.Column("token", sa.String(500), nullable=False),
        sa.Column("platform", sa.String(40), nullable=False, server_default="unknown"),
        sa.Column("status", sa.String(40), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "rounds",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("game_id", sa.String(64), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("creator_user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("guesser_user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("original_prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="generating"),
        sa.Column("clue_reveal_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "game_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("game_id", sa.String(64), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id")),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "generated_svgs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("round_id", sa.String(64), sa.ForeignKey("rounds.id"), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(160), nullable=False),
        sa.Column("model_tier", sa.String(40), nullable=False),
        sa.Column("svg_text", sa.Text()),
        sa.Column("generation_time_seconds", sa.Float()),
        sa.Column("status", sa.String(40), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "guesses",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("round_id", sa.String(64), sa.ForeignKey("rounds.id"), nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("guess_text", sa.Text(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("judge_result_json", sa.Text(), nullable=False),
        sa.Column("component_scores_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("clue_count_used", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "notification_attempts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("device_token_id", sa.String(64), sa.ForeignKey("device_tokens.id")),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(40), nullable=False, server_default="pending"),
        sa.Column("response_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("notification_attempts")
    op.drop_table("guesses")
    op.drop_table("generated_svgs")
    op.drop_table("game_events")
    op.drop_table("rounds")
    op.drop_table("device_tokens")
    op.drop_table("game_invites")
    op.drop_table("games")
    op.drop_table("users")
