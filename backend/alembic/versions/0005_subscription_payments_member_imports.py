"""Subscription payments and SMS top-ups sent to us; member register imports.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-19 23:55:26.393522
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "member_imports",
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("headers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rows", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["created_by"],
            ["staff_users.id"],
            name=op.f("fk_member_imports_created_by_staff_users"),
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_member_imports_gym_id_gyms")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_member_imports")),
    )
    op.create_index(
        op.f("ix_member_imports_gym_id"), "member_imports", ["gym_id"], unique=False
    )
    op.create_table(
        "subscription_payments",
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("platform_plan_id", sa.UUID(), nullable=True),
        sa.Column("months", sa.Integer(), nullable=True),
        sa.Column("sms_credits", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("transaction_ref", sa.String(length=64), nullable=True),
        sa.Column("screenshot_key", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("submitted_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
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
            ["gym_id"], ["gyms.id"], name=op.f("fk_subscription_payments_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["platform_plan_id"],
            ["platform_plans.id"],
            name=op.f("fk_subscription_payments_platform_plan_id_platform_plans"),
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["staff_users.id"],
            name=op.f("fk_subscription_payments_reviewed_by_staff_users"),
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by"],
            ["staff_users.id"],
            name=op.f("fk_subscription_payments_submitted_by_staff_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscription_payments")),
    )
    op.create_index(
        op.f("ix_subscription_payments_gym_id"),
        "subscription_payments",
        ["gym_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_subscription_payments_gym_id"), table_name="subscription_payments"
    )
    op.drop_table("subscription_payments")
    op.drop_index(op.f("ix_member_imports_gym_id"), table_name="member_imports")
    op.drop_table("member_imports")
