"""Visit packs and off-peak hours on plans, copied to memberships (PLAN.md §16.4, 9.3, 9.4).

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-17 16:44:45.785695
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("memberships", sa.Column("visit_limit", sa.Integer(), nullable=True))
    op.add_column(
        "memberships",
        sa.Column(
            "access_hours", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.add_column("plans", sa.Column("visit_limit", sa.Integer(), nullable=True))
    op.add_column(
        "plans",
        sa.Column(
            "access_hours", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    # "denied_visits_used" is longer than any result before it.
    op.alter_column(
        "check_ins",
        "result",
        type_=sa.String(length=24),
        existing_type=sa.String(length=16),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_plans_visit_limit", "plans", "visit_limit IS NULL OR visit_limit > 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_plans_visit_limit", "plans", type_="check")
    op.alter_column(
        "check_ins",
        "result",
        type_=sa.String(length=16),
        existing_type=sa.String(length=24),
        existing_nullable=False,
    )
    op.drop_column("plans", "access_hours")
    op.drop_column("plans", "visit_limit")
    op.drop_column("memberships", "access_hours")
    op.drop_column("memberships", "visit_limit")
