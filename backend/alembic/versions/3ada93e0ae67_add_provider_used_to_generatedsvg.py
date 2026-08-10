"""Add nullable provider_used provenance to generated SVGs.

Revision ID: 3ada93e0ae67
Revises: 20260701_0001
Create Date: 2026-07-05 19:25:26.518131
"""
from alembic import op
import sqlalchemy as sa


revision = "3ada93e0ae67"
down_revision = "20260701_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("generated_svgs", sa.Column("provider_used", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("generated_svgs", "provider_used")
