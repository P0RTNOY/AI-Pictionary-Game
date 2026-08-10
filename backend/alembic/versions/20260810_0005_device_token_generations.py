"""Add generation-aware device-token retirement.

Revision ID: 20260810_0005
Revises: 20260810_0004
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260810_0005"
down_revision = "20260810_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    device_token_columns = {
        column["name"] for column in inspector.get_columns("device_tokens")
    }
    if "registration_id" not in device_token_columns:
        op.add_column(
            "device_tokens",
            sa.Column("registration_id", sa.String(length=64), nullable=True),
        )
    index_names = {index["name"] for index in sa.inspect(bind).get_indexes("device_tokens")}
    if "ix_device_tokens_registration_id" not in index_names:
        op.create_index(
            "ix_device_tokens_registration_id",
            "device_tokens",
            ["registration_id"],
        )
    retirement_table_exists = "device_token_retirements" in sa.inspect(bind).get_table_names()
    if not retirement_table_exists:
        op.create_table(
            "device_token_retirements",
            sa.Column("registration_id", sa.String(length=64), primary_key=True),
            sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("provider", sa.String(length=40), nullable=False),
            sa.Column("token", sa.String(length=500), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    retirement_index_names = (
        {
            index["name"]
            for index in sa.inspect(bind).get_indexes("device_token_retirements")
        }
        if retirement_table_exists
        else set()
    )
    if "ix_device_token_retirements_user_id" not in retirement_index_names:
        op.create_index(
            "ix_device_token_retirements_user_id",
            "device_token_retirements",
            ["user_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "device_token_retirements" in inspector.get_table_names():
        retirement_index_names = {
            index["name"]
            for index in inspector.get_indexes("device_token_retirements")
        }
        if "ix_device_token_retirements_user_id" in retirement_index_names:
            op.drop_index(
                "ix_device_token_retirements_user_id",
                table_name="device_token_retirements",
            )
        op.drop_table("device_token_retirements")
    index_names = {index["name"] for index in sa.inspect(bind).get_indexes("device_tokens")}
    if "ix_device_tokens_registration_id" in index_names:
        op.drop_index("ix_device_tokens_registration_id", table_name="device_tokens")
    device_token_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("device_tokens")
    }
    if "registration_id" in device_token_columns:
        op.drop_column("device_tokens", "registration_id")
