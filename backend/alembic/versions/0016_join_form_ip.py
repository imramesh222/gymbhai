"""Enquiries from the public join form remember the sender's IP for a day (PLAN.md §16.4, 9.5).

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-17 16:50:58.706177
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("from_ip", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_leads_from_ip_created", "leads", ["from_ip", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_leads_from_ip_created", table_name="leads")
    op.drop_column("leads", "from_ip")
