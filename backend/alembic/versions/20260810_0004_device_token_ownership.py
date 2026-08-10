"""Enforce active device-token ownership and bounded lookup indexes.

Revision ID: 20260810_0004
Revises: 20260810_0003
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa

from app.config import ACTIVE_DEVICE_TOKEN_LIMIT


revision = "20260810_0004"
down_revision = "20260810_0003"
branch_labels = None
depends_on = None


ACTIVE_TOKEN_PREDICATE = "status = 'active'"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "task4_device_token_conflict_archive" not in inspector.get_table_names():
        op.create_table(
            "task4_device_token_conflict_archive",
            sa.Column("device_token_id", sa.String(length=64), primary_key=True),
            sa.Column("original_status", sa.String(length=40), nullable=False),
        )
    op.execute(
        sa.text(
            """
            INSERT INTO task4_device_token_conflict_archive
                (device_token_id, original_status)
            SELECT id, status
            FROM (
                SELECT id, status,
                       ROW_NUMBER() OVER (
                           PARTITION BY provider, token
                           ORDER BY updated_at DESC, created_at DESC, id DESC
                       ) AS task4_rank
                FROM device_tokens
                WHERE status = 'active'
            ) ranked
            WHERE task4_rank > 1
              AND NOT EXISTS (
                  SELECT 1 FROM task4_device_token_conflict_archive archive
                  WHERE archive.device_token_id = ranked.id
              )
            """
        )
    )
    op.execute(
        sa.text(
            "UPDATE device_tokens SET status = 'inactive' WHERE id IN ("
            "SELECT id FROM (SELECT id, ROW_NUMBER() OVER ("
            "PARTITION BY provider, token ORDER BY updated_at DESC, created_at DESC, id DESC"
            ") task4_rank FROM device_tokens WHERE status = 'active') ranked "
            "WHERE task4_rank > 1)"
        )
    )
    op.execute(
        sa.text(
            f"""
            INSERT INTO task4_device_token_conflict_archive
                (device_token_id, original_status)
            SELECT id, status
            FROM (
                SELECT id, status,
                       ROW_NUMBER() OVER (
                           PARTITION BY user_id
                           ORDER BY updated_at DESC, created_at DESC, id DESC
                       ) AS task4_rank
                FROM device_tokens
                WHERE status = 'active'
            ) ranked
            WHERE task4_rank > {ACTIVE_DEVICE_TOKEN_LIMIT}
              AND NOT EXISTS (
                  SELECT 1 FROM task4_device_token_conflict_archive archive
                  WHERE archive.device_token_id = ranked.id
              )
            """
        )
    )
    op.execute(
        sa.text(
            "UPDATE device_tokens SET status = 'inactive' WHERE id IN ("
            "SELECT id FROM (SELECT id, ROW_NUMBER() OVER ("
            "PARTITION BY user_id ORDER BY updated_at DESC, created_at DESC, id DESC"
            f") task4_rank FROM device_tokens WHERE status = 'active') ranked "
            f"WHERE task4_rank > {ACTIVE_DEVICE_TOKEN_LIMIT})"
        )
    )

    index_names = {index["name"] for index in sa.inspect(bind).get_indexes("device_tokens")}
    if "uq_device_tokens_active_provider_token" not in index_names:
        op.create_index(
            "uq_device_tokens_active_provider_token",
            "device_tokens",
            ["provider", "token"],
            unique=True,
            sqlite_where=sa.text(ACTIVE_TOKEN_PREDICATE),
            postgresql_where=sa.text(ACTIVE_TOKEN_PREDICATE),
        )
    if "ix_device_tokens_user_status" not in index_names:
        op.create_index(
            "ix_device_tokens_user_status",
            "device_tokens",
            ["user_id", "status"],
        )


def downgrade() -> None:
    op.drop_index("ix_device_tokens_user_status", table_name="device_tokens")
    op.drop_index("uq_device_tokens_active_provider_token", table_name="device_tokens")
    op.execute(
        sa.text(
            "UPDATE device_tokens SET status = ("
            "SELECT original_status FROM task4_device_token_conflict_archive "
            "WHERE task4_device_token_conflict_archive.device_token_id = device_tokens.id"
            ") WHERE id IN (SELECT device_token_id FROM task4_device_token_conflict_archive)"
        )
    )
    op.drop_table("task4_device_token_conflict_archive")
