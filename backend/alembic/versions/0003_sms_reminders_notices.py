"""SMS messages and credits, reminder rules and log, notices, scheduled runs.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-19 08:22:42.314967
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduled_runs",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("run_on", sa.Date(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scheduled_runs")),
        sa.UniqueConstraint("name", "run_on", name=op.f("uq_scheduled_runs_name")),
    )
    op.create_table(
        "reminder_rules",
        sa.Column("days_from_expiry", sa.Integer(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
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
        sa.Column("gym_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_reminder_rules_gym_id_gyms")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reminder_rules")),
        sa.UniqueConstraint(
            "gym_id", "days_from_expiry", name=op.f("uq_reminder_rules_gym_id")
        ),
    )
    op.create_index(
        op.f("ix_reminder_rules_gym_id"), "reminder_rules", ["gym_id"], unique=False
    )
    op.create_table(
        "notices",
        sa.Column("branch_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("send_sms", sa.Boolean(), nullable=False),
        sa.Column(
            "sms_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
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
        sa.Column("gym_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["branch_id"], ["branches.id"], name=op.f("fk_notices_branch_id_branches")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["staff_users.id"],
            name=op.f("fk_notices_created_by_staff_users"),
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_notices_gym_id_gyms")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notices")),
    )
    op.create_index(op.f("ix_notices_gym_id"), "notices", ["gym_id"], unique=False)
    op.create_index(
        "ix_notices_gym_published", "notices", ["gym_id", "published_at"], unique=False
    )
    op.create_table(
        "sms_messages",
        sa.Column("member_id", sa.UUID(), nullable=True),
        sa.Column("to", sa.String(length=10), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=True),
        sa.Column("provider_ref", sa.String(length=64), nullable=True),
        sa.Column("segments", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("gym_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["staff_users.id"],
            name=op.f("fk_sms_messages_created_by_staff_users"),
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_sms_messages_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["members.id"],
            name=op.f("fk_sms_messages_member_id_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sms_messages")),
    )
    op.create_index(
        "ix_sms_messages_gym_created",
        "sms_messages",
        ["gym_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_sms_messages_gym_id"), "sms_messages", ["gym_id"], unique=False
    )
    op.create_index(
        op.f("ix_sms_messages_member_id"), "sms_messages", ["member_id"], unique=False
    )
    op.create_table(
        "reminder_log",
        sa.Column("rule_id", sa.UUID(), nullable=False),
        sa.Column("membership_id", sa.UUID(), nullable=False),
        sa.Column("sms_message_id", sa.UUID(), nullable=True),
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
            ["gym_id"], ["gyms.id"], name=op.f("fk_reminder_log_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            ["memberships.id"],
            name=op.f("fk_reminder_log_membership_id_memberships"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["reminder_rules.id"],
            name=op.f("fk_reminder_log_rule_id_reminder_rules"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sms_message_id"],
            ["sms_messages.id"],
            name=op.f("fk_reminder_log_sms_message_id_sms_messages"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reminder_log")),
        sa.UniqueConstraint(
            "rule_id", "membership_id", name=op.f("uq_reminder_log_rule_id")
        ),
    )
    op.create_index(
        op.f("ix_reminder_log_gym_id"), "reminder_log", ["gym_id"], unique=False
    )
    op.create_index(
        op.f("ix_reminder_log_membership_id"),
        "reminder_log",
        ["membership_id"],
        unique=False,
    )
    op.create_table(
        "sms_credit_ledger",
        sa.Column("change", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("sms_message_id", sa.UUID(), nullable=True),
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
            ["gym_id"], ["gyms.id"], name=op.f("fk_sms_credit_ledger_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["sms_message_id"],
            ["sms_messages.id"],
            name=op.f("fk_sms_credit_ledger_sms_message_id_sms_messages"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sms_credit_ledger")),
    )
    op.create_index(
        "ix_sms_credit_ledger_gym_created",
        "sms_credit_ledger",
        ["gym_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_sms_credit_ledger_gym_id"),
        "sms_credit_ledger",
        ["gym_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_sms_credit_ledger_gym_id"), table_name="sms_credit_ledger")
    op.drop_index("ix_sms_credit_ledger_gym_created", table_name="sms_credit_ledger")
    op.drop_table("sms_credit_ledger")
    op.drop_index(op.f("ix_reminder_log_membership_id"), table_name="reminder_log")
    op.drop_index(op.f("ix_reminder_log_gym_id"), table_name="reminder_log")
    op.drop_table("reminder_log")
    op.drop_index(op.f("ix_sms_messages_member_id"), table_name="sms_messages")
    op.drop_index(op.f("ix_sms_messages_gym_id"), table_name="sms_messages")
    op.drop_index("ix_sms_messages_gym_created", table_name="sms_messages")
    op.drop_table("sms_messages")
    op.drop_index("ix_notices_gym_published", table_name="notices")
    op.drop_index(op.f("ix_notices_gym_id"), table_name="notices")
    op.drop_table("notices")
    op.drop_index(op.f("ix_reminder_rules_gym_id"), table_name="reminder_rules")
    op.drop_table("reminder_rules")
    op.drop_table("scheduled_runs")
