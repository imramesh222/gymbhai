"""The phone app: app sessions, native push tokens, members' idempotency keys (PLAN.md §17.2).

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-17 22:10:00.271330
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("idempotency_keys", sa.Column("member_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_idempotency_keys_member_id_members"),
        "idempotency_keys",
        "members",
        ["member_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.add_column(
        "member_sessions",
        sa.Column("client", sa.String(length=8), server_default="web", nullable=False),
    )
    op.add_column(
        "push_subscriptions",
        sa.Column("kind", sa.String(length=8), server_default="web", nullable=False),
    )
    op.add_column(
        "push_subscriptions",
        sa.Column("expo_token", sa.String(length=255), nullable=True),
    )
    op.alter_column(
        "push_subscriptions", "endpoint", existing_type=sa.TEXT(), nullable=True
    )
    op.alter_column(
        "push_subscriptions",
        "p256dh",
        existing_type=sa.VARCHAR(length=200),
        nullable=True,
    )
    op.alter_column(
        "push_subscriptions",
        "auth",
        existing_type=sa.VARCHAR(length=100),
        nullable=True,
    )
    op.create_unique_constraint(
        "uq_push_subscriptions_member_expo_token",
        "push_subscriptions",
        ["member_id", "expo_token"],
    )
    op.create_check_constraint(
        "ck_push_subscriptions_kind_fields",
        "push_subscriptions",
        "(kind = 'web' AND endpoint IS NOT NULL AND p256dh IS NOT NULL"
        " AND auth IS NOT NULL) OR (kind = 'expo' AND expo_token IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_push_subscriptions_kind_fields", "push_subscriptions", type_="check"
    )
    # The web-only columns become required again: the app's tokens go.
    op.execute("DELETE FROM push_subscriptions WHERE kind <> 'web'")
    op.drop_constraint(
        "uq_push_subscriptions_member_expo_token", "push_subscriptions", type_="unique"
    )
    op.alter_column(
        "push_subscriptions",
        "auth",
        existing_type=sa.VARCHAR(length=100),
        nullable=False,
    )
    op.alter_column(
        "push_subscriptions",
        "p256dh",
        existing_type=sa.VARCHAR(length=200),
        nullable=False,
    )
    op.alter_column(
        "push_subscriptions", "endpoint", existing_type=sa.TEXT(), nullable=False
    )
    op.drop_column("push_subscriptions", "expo_token")
    op.drop_column("push_subscriptions", "kind")
    op.drop_column("member_sessions", "client")
    op.drop_constraint(
        op.f("fk_idempotency_keys_member_id_members"),
        "idempotency_keys",
        type_="foreignkey",
    )
    op.drop_column("idempotency_keys", "member_id")
