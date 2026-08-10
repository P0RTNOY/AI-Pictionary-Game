"""Add beta sessions, generation admission gate, and transition invariants.

Revision ID: 20260810_0003
Revises: 3ada93e0ae67
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260810_0003"
down_revision = "3ada93e0ae67"
branch_labels = None
depends_on = None


ACTIVE_ROUND_PREDICATE = "status IN ('generating', 'ready_to_guess')"


def upgrade() -> None:
    op.add_column("users", sa.Column("session_token_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_users_session_token_hash", "users", ["session_token_hash"], unique=True)

    op.create_table(
        "generation_admission_gate",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(sa.text("INSERT INTO generation_admission_gate (id, version) VALUES (1, 0)"))

    op.create_table(
        "websocket_tickets",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("ticket_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("game_id", sa.String(length=64), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_websocket_tickets_ticket_hash", "websocket_tickets", ["ticket_hash"], unique=True)
    op.create_index("ix_websocket_tickets_user_id", "websocket_tickets", ["user_id"])
    op.create_index("ix_websocket_tickets_game_id", "websocket_tickets", ["game_id"])

    op.create_table(
        "task3_guess_conflict_archive",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("round_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("guess_text", sa.Text(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("judge_result_json", sa.Text(), nullable=False),
        sa.Column("component_scores_json", sa.Text(), nullable=False),
        sa.Column("clue_count_used", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO task3_guess_conflict_archive
                (id, round_id, user_id, guess_text, score, judge_result_json,
                 component_scores_json, clue_count_used, created_at, updated_at)
            SELECT id, round_id, user_id, guess_text, score, judge_result_json,
                   component_scores_json, clue_count_used, created_at, updated_at
            FROM (
                SELECT guesses.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY round_id ORDER BY created_at ASC, id ASC
                       ) AS task3_rank
                FROM guesses
            ) ranked
            WHERE task3_rank > 1
            """
        )
    )
    op.execute(sa.text("DELETE FROM guesses WHERE id IN (SELECT id FROM task3_guess_conflict_archive)"))

    op.create_table(
        "task3_active_round_archive",
        sa.Column("round_id", sa.String(length=64), primary_key=True),
        sa.Column("original_status", sa.String(length=40), nullable=False),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO task3_active_round_archive (round_id, original_status)
            SELECT id, status
            FROM (
                SELECT id, status,
                       ROW_NUMBER() OVER (
                           PARTITION BY game_id ORDER BY created_at ASC, id ASC
                       ) AS task3_rank
                FROM rounds
                WHERE status IN ('generating', 'ready_to_guess')
            ) ranked
            WHERE task3_rank > 1
            """
        )
    )
    op.execute(
        sa.text(
            "UPDATE rounds SET status = 'failed' "
            "WHERE id IN (SELECT round_id FROM task3_active_round_archive)"
        )
    )

    op.create_index("uq_guesses_round_id", "guesses", ["round_id"], unique=True)
    op.create_index(
        "uq_rounds_one_active_per_game",
        "rounds",
        ["game_id"],
        unique=True,
        sqlite_where=sa.text(ACTIVE_ROUND_PREDICATE),
        postgresql_where=sa.text(ACTIVE_ROUND_PREDICATE),
    )


def downgrade() -> None:
    op.drop_index("uq_rounds_one_active_per_game", table_name="rounds")
    op.drop_index("uq_guesses_round_id", table_name="guesses")

    op.execute(
        sa.text(
            """
            INSERT INTO guesses
                (id, round_id, user_id, guess_text, score, judge_result_json,
                 component_scores_json, clue_count_used, created_at, updated_at)
            SELECT id, round_id, user_id, guess_text, score, judge_result_json,
                   component_scores_json, clue_count_used, created_at, updated_at
            FROM task3_guess_conflict_archive
            """
        )
    )
    op.execute(
        sa.text(
            "UPDATE rounds SET status = ("
            "SELECT original_status FROM task3_active_round_archive "
            "WHERE task3_active_round_archive.round_id = rounds.id"
            ") WHERE id IN (SELECT round_id FROM task3_active_round_archive)"
        )
    )
    op.drop_table("task3_active_round_archive")
    op.drop_table("task3_guess_conflict_archive")

    op.drop_index("ix_websocket_tickets_game_id", table_name="websocket_tickets")
    op.drop_index("ix_websocket_tickets_user_id", table_name="websocket_tickets")
    op.drop_index("ix_websocket_tickets_ticket_hash", table_name="websocket_tickets")
    op.drop_table("websocket_tickets")
    op.drop_table("generation_admission_gate")

    op.drop_index("ix_users_session_token_hash", table_name="users")
    op.drop_column("users", "session_token_hash")
