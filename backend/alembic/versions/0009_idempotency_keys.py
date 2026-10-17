"""Answers to money requests, so a repeat isn't a second payment (PLAN.md §16.1).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-17 06:49:25.270701
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("route", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("gym_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_idempotency_keys_gym_id_gyms")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_keys")),
        sa.UniqueConstraint("gym_id", "key", name=op.f("uq_idempotency_keys_gym_id")),
    )
    op.create_index(
        op.f("ix_idempotency_keys_gym_id"), "idempotency_keys", ["gym_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_idempotency_keys_gym_id"), table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
