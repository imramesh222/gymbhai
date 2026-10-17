"""Terms accepted at sign-up; members erased at their request (PLAN.md §16.1).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-17 07:43:05.638167
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "gyms",
        sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "gyms", sa.Column("terms_version", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "members", sa.Column("erased_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("members", "erased_at")
    op.drop_column("gyms", "terms_version")
    op.drop_column("gyms", "terms_accepted_at")
