"""Staff sign-in tries, for the limits on guessing passwords (PLAN.md §16.1).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-17 01:17:17.819127
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_attempts",
        sa.Column("identifier", sa.String(length=254), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_attempts")),
    )
    op.create_index(
        "ix_login_attempts_identifier_at",
        "login_attempts",
        ["identifier", "at"],
        unique=False,
    )
    op.create_index(
        "ix_login_attempts_ip_at", "login_attempts", ["ip", "at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_login_attempts_ip_at", table_name="login_attempts")
    op.drop_index("ix_login_attempts_identifier_at", table_name="login_attempts")
    op.drop_table("login_attempts")
