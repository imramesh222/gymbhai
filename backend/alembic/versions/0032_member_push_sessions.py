"""A member's push subscription belongs to the sign-in that turned it on
(PLAN.md §17.5): signing that device out turns its notifications off.

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-21 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "push_subscriptions", sa.Column("session_id", sa.UUID(), nullable=True)
    )
    op.create_index(
        op.f("ix_push_subscriptions_session_id"),
        "push_subscriptions",
        ["session_id"],
    )
    op.create_foreign_key(
        op.f("fk_push_subscriptions_session_id_member_sessions"),
        "push_subscriptions",
        "member_sessions",
        ["session_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_push_subscriptions_session_id_member_sessions"),
        "push_subscriptions",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_push_subscriptions_session_id"), table_name="push_subscriptions"
    )
    op.drop_column("push_subscriptions", "session_id")
