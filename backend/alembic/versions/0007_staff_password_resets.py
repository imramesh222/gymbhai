"""Forgot password codes for staff (PLAN.md §16.1).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-17 01:24:31.261755
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_password_resets",
        sa.Column("staff_user_id", sa.UUID(), nullable=True),
        sa.Column("identifier", sa.String(length=254), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "attempts", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
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
            ["staff_user_id"],
            ["staff_users.id"],
            name=op.f("fk_staff_password_resets_staff_user_id_staff_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_password_resets")),
    )
    op.create_index(
        "ix_staff_password_resets_identifier_created",
        "staff_password_resets",
        ["identifier", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_staff_password_resets_ip_created",
        "staff_password_resets",
        ["ip", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staff_password_resets_staff_user_id"),
        "staff_password_resets",
        ["staff_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_staff_password_resets_staff_user_id"),
        table_name="staff_password_resets",
    )
    op.drop_index(
        "ix_staff_password_resets_ip_created", table_name="staff_password_resets"
    )
    op.drop_index(
        "ix_staff_password_resets_identifier_created",
        table_name="staff_password_resets",
    )
    op.drop_table("staff_password_resets")
