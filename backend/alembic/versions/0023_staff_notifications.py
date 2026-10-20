"""Notifications for staff: their browsers, and the kinds they turned off
(PLAN.md §18.6).

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-19 16:49:06.108754
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_push_subscriptions",
        sa.Column("staff_user_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(length=200), nullable=False),
        sa.Column("auth", sa.String(length=100), nullable=False),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("last_ok_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["staff_sessions.id"],
            name=op.f("fk_staff_push_subscriptions_session_id_staff_sessions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["staff_user_id"],
            ["staff_users.id"],
            name=op.f("fk_staff_push_subscriptions_staff_user_id_staff_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_push_subscriptions")),
        sa.UniqueConstraint(
            "staff_user_id", "endpoint", name="uq_staff_push_subscriptions_staff"
        ),
    )
    op.create_index(
        op.f("ix_staff_push_subscriptions_session_id"),
        "staff_push_subscriptions",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staff_push_subscriptions_staff_user_id"),
        "staff_push_subscriptions",
        ["staff_user_id"],
        unique=False,
    )
    op.add_column(
        "staff_users",
        sa.Column(
            "muted_notifications",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("staff_users", "muted_notifications")
    op.drop_index(
        op.f("ix_staff_push_subscriptions_staff_user_id"),
        table_name="staff_push_subscriptions",
    )
    op.drop_index(
        op.f("ix_staff_push_subscriptions_session_id"),
        table_name="staff_push_subscriptions",
    )
    op.drop_table("staff_push_subscriptions")
