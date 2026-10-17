"""Nepali: a language for each staff account, member and gym (PLAN.md §16.6).

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-17 17:28:01.611514
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("members", sa.Column("language", sa.String(length=2), nullable=True))
    op.add_column(
        "staff_users", sa.Column("language", sa.String(length=2), nullable=True)
    )
    # The gym's language replaces reminder_language, which nothing read.
    op.execute(
        "UPDATE gyms SET settings = (settings - 'reminder_language')"
        " || jsonb_build_object('language', COALESCE(settings->>'reminder_language', 'en'),"
        " 'digits', 'western')"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE gyms SET settings = (settings - 'language' - 'digits')"
        " || jsonb_build_object('reminder_language', COALESCE(settings->>'language', 'en'))"
    )
    op.drop_column("staff_users", "language")
    op.drop_column("members", "language")
