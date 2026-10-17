"""Web Push subscriptions for the member app; notices count pushes (PLAN.md §16.3, 8.3).

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-17 12:09:34.538679
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("member_id", sa.UUID(), nullable=False),
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
        sa.Column("gym_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_push_subscriptions_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["members.id"],
            name=op.f("fk_push_subscriptions_member_id_members"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_subscriptions")),
        sa.UniqueConstraint(
            "member_id", "endpoint", name=op.f("uq_push_subscriptions_member_id")
        ),
    )
    op.create_index(
        op.f("ix_push_subscriptions_gym_id"),
        "push_subscriptions",
        ["gym_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_push_subscriptions_member_id"),
        "push_subscriptions",
        ["member_id"],
        unique=False,
    )
    op.add_column(
        "notices",
        sa.Column(
            "push_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("notices", "push_count")
    op.drop_index(
        op.f("ix_push_subscriptions_member_id"), table_name="push_subscriptions"
    )
    op.drop_index(op.f("ix_push_subscriptions_gym_id"), table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
