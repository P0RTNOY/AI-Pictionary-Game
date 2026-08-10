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

    with op.batch_alter_table("game_invites") as batch_op:
        batch_op.alter_column(
            "code",
            existing_type=sa.String(length=24),
            type_=sa.String(length=64),
            existing_nullable=False,
        )

    op.create_table(
        "generation_admission_gate",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(sa.text("INSERT INTO generation_admission_gate (id, version) VALUES (1, 0)"))

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
    op.drop_table("generation_admission_gate")

    with op.batch_alter_table("game_invites") as batch_op:
        batch_op.alter_column(
            "code",
            existing_type=sa.String(length=64),
            type_=sa.String(length=24),
            existing_nullable=False,
        )

    op.drop_index("ix_users_session_token_hash", table_name="users")
    op.drop_column("users", "session_token_hash")
