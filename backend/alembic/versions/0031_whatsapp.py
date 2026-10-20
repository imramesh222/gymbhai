"""WhatsApp messages (PLAN.md §19.3): the channel and Meta's delivery reports
on each message, members agreeing, and what a WhatsApp message costs.

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-21 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sms_messages",
        sa.Column("channel", sa.String(length=8), server_default="sms", nullable=False),
    )
    op.add_column(
        "sms_messages", sa.Column("template", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "sms_messages",
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("sms_messages", sa.Column("fallback", sa.Text(), nullable=True))
    op.add_column(
        "sms_messages",
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sms_messages", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.alter_column(
        "sms_messages",
        "provider_ref",
        existing_type=sa.String(length=64),
        type_=sa.String(length=128),
        existing_nullable=True,
    )
    op.create_index(
        "ix_sms_messages_provider_ref",
        "sms_messages",
        ["provider_ref"],
        postgresql_where=sa.text("provider_ref IS NOT NULL"),
    )
    op.add_column(
        "members",
        sa.Column("whatsapp_agreed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "members",
        sa.Column("whatsapp_unreachable_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "platform_settings",
        sa.Column(
            "whatsapp_credits",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_settings")),
    )


def downgrade() -> None:
    op.drop_table("platform_settings")
    op.drop_column("members", "whatsapp_unreachable_at")
    op.drop_column("members", "whatsapp_agreed_at")
    op.drop_index(
        "ix_sms_messages_provider_ref",
        table_name="sms_messages",
        postgresql_where=sa.text("provider_ref IS NOT NULL"),
    )
    op.alter_column(
        "sms_messages",
        "provider_ref",
        existing_type=sa.String(length=128),
        type_=sa.String(length=64),
        existing_nullable=True,
    )
    op.drop_column("sms_messages", "read_at")
    op.drop_column("sms_messages", "delivered_at")
    op.drop_column("sms_messages", "fallback")
    op.drop_column("sms_messages", "params")
    op.drop_column("sms_messages", "template")
    op.drop_column("sms_messages", "channel")
