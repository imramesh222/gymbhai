"""What's new and gym referrals (PLAN.md §16.5, 10.4, 10.5).

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-17 17:08:13.022084
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "changelog_entries",
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
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
            ["created_by"],
            ["staff_users.id"],
            name=op.f("fk_changelog_entries_created_by_staff_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_changelog_entries")),
    )
    op.create_index(
        op.f("ix_changelog_entries_published_at"),
        "changelog_entries",
        ["published_at"],
        unique=False,
    )
    op.create_table(
        "gym_referrals",
        sa.Column("referred_gym_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
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
            ["gym_id"], ["gyms.id"], name=op.f("fk_gym_referrals_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["referred_gym_id"],
            ["gyms.id"],
            name=op.f("fk_gym_referrals_referred_gym_id_gyms"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["staff_users.id"],
            name=op.f("fk_gym_referrals_reviewed_by_staff_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gym_referrals")),
        sa.UniqueConstraint(
            "referred_gym_id", name=op.f("uq_gym_referrals_referred_gym_id")
        ),
    )
    op.create_index(
        op.f("ix_gym_referrals_gym_id"), "gym_referrals", ["gym_id"], unique=False
    )
    op.add_column(
        "staff_users",
        sa.Column("changelog_seen_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("staff_users", "changelog_seen_at")
    op.drop_index(op.f("ix_gym_referrals_gym_id"), table_name="gym_referrals")
    op.drop_table("gym_referrals")
    op.drop_index(
        op.f("ix_changelog_entries_published_at"), table_name="changelog_entries"
    )
    op.drop_table("changelog_entries")
