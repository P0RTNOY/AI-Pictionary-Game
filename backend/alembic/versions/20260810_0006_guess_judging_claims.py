"""Add non-blocking, owned guess-judging claims.

Revision ID: 20260810_0006
Revises: 20260810_0005
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260810_0006"
down_revision = "20260810_0005"
branch_labels = None
depends_on = None


ACTIVE_ROUND_PREDICATE = "status IN ('generating', 'ready_to_guess', 'judging')"
PREVIOUS_ACTIVE_ROUND_PREDICATE = "status IN ('generating', 'ready_to_guess')"


def _drop_active_round_index_if_present() -> None:
    bind = op.get_bind()
    index_names = {index["name"] for index in sa.inspect(bind).get_indexes("rounds")}
    if "uq_rounds_one_active_per_game" in index_names:
        op.drop_index("uq_rounds_one_active_per_game", table_name="rounds")


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("rounds")}
    if "guess_claim_id" not in columns:
        op.add_column("rounds", sa.Column("guess_claim_id", sa.String(length=64), nullable=True))
    _drop_active_round_index_if_present()
    op.create_index(
        "uq_rounds_one_active_per_game",
        "rounds",
        ["game_id"],
        unique=True,
        sqlite_where=sa.text(ACTIVE_ROUND_PREDICATE),
        postgresql_where=sa.text(ACTIVE_ROUND_PREDICATE),
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE rounds SET status = 'ready_to_guess', guess_claim_id = NULL "
            "WHERE status = 'judging'"
        )
    )
    _drop_active_round_index_if_present()
    op.create_index(
        "uq_rounds_one_active_per_game",
        "rounds",
        ["game_id"],
        unique=True,
        sqlite_where=sa.text(PREVIOUS_ACTIVE_ROUND_PREDICATE),
        postgresql_where=sa.text(PREVIOUS_ACTIVE_ROUND_PREDICATE),
    )
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("rounds")}
    if "guess_claim_id" in columns:
        op.drop_column("rounds", "guess_claim_id")
