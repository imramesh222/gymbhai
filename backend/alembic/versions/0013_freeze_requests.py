"""Freeze requests from the member app (PLAN.md §16.3, 8.6).

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-17 16:06:21.904793
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "freeze_requests",
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("membership_id", sa.UUID(), nullable=False),
        sa.Column("from_date", sa.Date(), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("freeze_id", sa.UUID(), nullable=True),
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
            ["freeze_id"],
            ["membership_freezes.id"],
            name=op.f("fk_freeze_requests_freeze_id_membership_freezes"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_freeze_requests_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["members.id"],
            name=op.f("fk_freeze_requests_member_id_members"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            ["memberships.id"],
            name=op.f("fk_freeze_requests_membership_id_memberships"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["staff_users.id"],
            name=op.f("fk_freeze_requests_reviewed_by_staff_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_freeze_requests")),
    )
    op.create_index(
        op.f("ix_freeze_requests_gym_id"), "freeze_requests", ["gym_id"], unique=False
    )
    op.create_index(
        "ix_freeze_requests_gym_status",
        "freeze_requests",
        ["gym_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_freeze_requests_member_id"),
        "freeze_requests",
        ["member_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_freeze_requests_member_id"), table_name="freeze_requests")
    op.drop_index("ix_freeze_requests_gym_status", table_name="freeze_requests")
    op.drop_index(op.f("ix_freeze_requests_gym_id"), table_name="freeze_requests")
    op.drop_table("freeze_requests")
