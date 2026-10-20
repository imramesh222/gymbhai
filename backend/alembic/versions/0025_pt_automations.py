"""Personal training automations: when it ends, and money owed (PLAN.md §18.3).

Every gym gets them switched off, in its own language, as a new gym does.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-20 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Kept here, not imported: a migration must not change when the app does.
# (trigger, days, English, Nepali)
NEW_RULES = (
    (
        "pt_ending",
        -3,
        "Hi {name}, your personal training at {gym} ends on {end_date}. "
        "To keep training with {trainer}, renew at the desk.",
        "नमस्ते {name}, {gym} मा {trainer} सँगको ट्रेनिङ {end_date} मा सकिँदैछ। नवीकरण डेस्कमा।",
    ),
    (
        "pt_ending",
        1,
        "Hi {name}, your personal training at {gym} ended on {end_date}. "
        "To keep training with {trainer}, renew at the desk.",
        "नमस्ते {name}, {gym} मा {trainer} सँगको ट्रेनिङ {end_date} मा सकियो। नवीकरण डेस्कमा।",
    ),
    (
        "pt_dues",
        7,
        "Hi {name}, a reminder from {gym}: Rs {amount} is still to pay "
        "for your personal training. Pay at the desk.",
        "नमस्ते {name}, {gym} मा पर्सनल ट्रेनिङको रु {amount} तिर्न बाँकी छ। डेस्कमा तिर्नुहोस्।",
    ),
)


def upgrade() -> None:
    op.execute(
        sa.text(
            "INSERT INTO reminder_rules"
            " (id, gym_id, trigger, days, template, enabled, created_at, updated_at)"
            " SELECT gen_random_uuid(), g.id, r.trigger, r.days,"
            " CASE WHEN g.settings->>'language' = 'ne' THEN r.ne ELSE r.en END,"
            " false, now(), now()"
            " FROM gyms g CROSS JOIN (VALUES "
            + ", ".join(f"(:t{i}, :d{i}, :e{i}, :n{i})" for i in range(len(NEW_RULES)))
            + ") AS r(trigger, days, en, ne)"
            " ON CONFLICT DO NOTHING"
        ).bindparams(
            **{
                key: value
                for i, (trigger, days, en, ne) in enumerate(NEW_RULES)
                for key, value in (
                    (f"t{i}", trigger),
                    (f"d{i}", days),
                    (f"e{i}", en),
                    (f"n{i}", ne),
                )
            }
        )
    )


def downgrade() -> None:
    # Their reminder_log rows go with them (ON DELETE CASCADE).
    op.execute("DELETE FROM reminder_rules WHERE trigger IN ('pt_ending', 'pt_dues')")
