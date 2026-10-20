"""The kiosk offline: check-ins it decided with no internet (PLAN.md §19.2).

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-20 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "check_ins",
        sa.Column(
            "offline", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.add_column(
        "check_ins", sa.Column("client_id", sa.String(length=64), nullable=True)
    )
    op.create_index(
        "uq_check_ins_device_client",
        "check_ins",
        ["device_id", "client_id"],
        unique=True,
        postgresql_where=sa.text("client_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_check_ins_device_client",
        table_name="check_ins",
        postgresql_where=sa.text("client_id IS NOT NULL"),
    )
    op.drop_column("check_ins", "client_id")
    op.drop_column("check_ins", "offline")
