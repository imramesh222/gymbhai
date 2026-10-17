"""Two-step sign-in for staff: authenticator nonce and recovery codes (PLAN.md §16.1).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-17 05:09:50.808942
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_recovery_codes",
        sa.Column("staff_user_id", sa.UUID(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["staff_user_id"],
            ["staff_users.id"],
            name=op.f("fk_staff_recovery_codes_staff_user_id_staff_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_recovery_codes")),
    )
    op.create_index(
        op.f("ix_staff_recovery_codes_staff_user_id"),
        "staff_recovery_codes",
        ["staff_user_id"],
        unique=False,
    )
    op.add_column(
        "staff_users", sa.Column("totp_nonce", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "staff_users",
        sa.Column("totp_enabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "staff_users", sa.Column("totp_last_step", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("staff_users", "totp_last_step")
    op.drop_column("staff_users", "totp_enabled_at")
    op.drop_column("staff_users", "totp_nonce")
    op.drop_index(
        op.f("ix_staff_recovery_codes_staff_user_id"), table_name="staff_recovery_codes"
    )
    op.drop_table("staff_recovery_codes")
