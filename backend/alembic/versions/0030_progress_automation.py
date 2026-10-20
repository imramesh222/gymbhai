"""Progress: the check-up reminder, by push only (PLAN.md §19.5).

Every gym gets it switched off, in its own language, as a new gym does.

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-20 23:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Kept here, not imported: a migration must not change when the app does.
DAYS = 30
EN = (
    "Hi {name}, it's been {days} days since your last check at {gym}. "
    "Time to weigh and measure, and see how far you've come!"
)
NE = "नमस्ते {name}, {gym} मा अन्तिम जाँचको {days} दिन भयो। तौल र नाप लिएर आफ्नो प्रगति हेर्नुहोस्!"


def upgrade() -> None:
    op.execute(
        sa.text(
            "INSERT INTO reminder_rules"
            " (id, gym_id, trigger, days, template, enabled, created_at, updated_at)"
            " SELECT gen_random_uuid(), g.id, 'progress', :days,"
            " CASE WHEN g.settings->>'language' = 'ne' THEN :ne ELSE :en END,"
            " false, now(), now()"
            " FROM gyms g"
            " ON CONFLICT DO NOTHING"
        ).bindparams(days=DAYS, en=EN, ne=NE)
    )


def downgrade() -> None:
    # Their reminder_log rows go with them (ON DELETE CASCADE).
    op.execute("DELETE FROM reminder_rules WHERE trigger = 'progress'")
