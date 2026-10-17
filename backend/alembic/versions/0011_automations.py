"""Automations: reminder rules get a trigger; the log a dedupe key (PLAN.md §16.3, 8.2).

Every gym also gets the new automations, switched off: win-back, dues,
not visiting and birthday. Only expiry reminders stay on by default.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-17 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Kept here, not imported: a migration must not change when the app does.
NEW_RULES = (
    (
        "lapsed",
        30,
        "Hi {name}, we haven't seen you at {gym} since your membership ended. "
        "Come back any time: {link}",
    ),
    (
        "dues",
        7,
        "Hi {name}, a reminder from {gym}: Rs {amount} is still to pay. "
        "Pay at the desk or in your app: {link}",
    ),
    (
        "not_visiting",
        14,
        "Hi {name}, we've missed you at {gym}! It's been {days} days. "
        "Your membership runs until {end_date}.",
    ),
    (
        "birthday",
        0,
        "Happy birthday, {name}! Have a great day. From all of us at {gym}",
    ),
)


def upgrade() -> None:
    op.drop_constraint("uq_reminder_rules_gym_id", "reminder_rules", type_="unique")
    op.alter_column("reminder_rules", "days_from_expiry", new_column_name="days")
    op.add_column(
        "reminder_rules",
        sa.Column(
            "trigger", sa.String(length=16), server_default="expiry", nullable=False
        ),
    )
    op.create_unique_constraint(
        op.f("uq_reminder_rules_gym_id"),
        "reminder_rules",
        ["gym_id", "trigger", "days"],
    )
    op.execute(
        sa.text(
            "INSERT INTO reminder_rules"
            " (id, gym_id, trigger, days, template, enabled, created_at, updated_at)"
            " SELECT gen_random_uuid(), g.id, r.trigger, r.days, r.template, false,"
            " now(), now()"
            " FROM gyms g CROSS JOIN (VALUES "
            + ", ".join(f"(:t{i}, :d{i}, :x{i})" for i in range(len(NEW_RULES)))
            + ") AS r(trigger, days, template)"
            " ON CONFLICT DO NOTHING"
        ).bindparams(
            **{
                key: value
                for i, (trigger, days, template) in enumerate(NEW_RULES)
                for key, value in (
                    (f"t{i}", trigger),
                    (f"d{i}", days),
                    (f"x{i}", template),
                )
            }
        )
    )

    op.add_column(
        "reminder_log", sa.Column("dedupe_key", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "reminder_log",
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        "UPDATE reminder_log l SET dedupe_key = 'membership:' || l.membership_id,"
        " member_id = m.member_id FROM memberships m WHERE m.id = l.membership_id"
    )
    op.alter_column("reminder_log", "dedupe_key", nullable=False)
    op.alter_column("reminder_log", "membership_id", nullable=True)
    op.drop_constraint("uq_reminder_log_rule_id", "reminder_log", type_="unique")
    op.create_unique_constraint(
        op.f("uq_reminder_log_rule_id"), "reminder_log", ["rule_id", "dedupe_key"]
    )
    op.create_index(
        op.f("ix_reminder_log_member_id"), "reminder_log", ["member_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_reminder_log_member_id_members"),
        "reminder_log",
        "members",
        ["member_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_reminder_log_member_id_members"), "reminder_log", type_="foreignkey"
    )
    op.drop_index(op.f("ix_reminder_log_member_id"), table_name="reminder_log")
    op.drop_constraint("uq_reminder_log_rule_id", "reminder_log", type_="unique")
    op.execute("DELETE FROM reminder_log WHERE membership_id IS NULL")
    op.alter_column("reminder_log", "membership_id", nullable=False)
    op.create_unique_constraint(
        "uq_reminder_log_rule_id", "reminder_log", ["rule_id", "membership_id"]
    )
    op.drop_column("reminder_log", "member_id")
    op.drop_column("reminder_log", "dedupe_key")

    op.drop_constraint("uq_reminder_rules_gym_id", "reminder_rules", type_="unique")
    op.execute("DELETE FROM reminder_rules WHERE trigger <> 'expiry'")
    op.drop_column("reminder_rules", "trigger")
    op.alter_column("reminder_rules", "days", new_column_name="days_from_expiry")
    op.create_unique_constraint(
        "uq_reminder_rules_gym_id", "reminder_rules", ["gym_id", "days_from_expiry"]
    )
