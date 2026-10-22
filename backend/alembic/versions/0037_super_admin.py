"""The super admin (PLAN.md §7 /admin): the platform admin with every /admin
permission, who adds the other admins and ticks what each may do. Every admin
until now could do everything, so each one becomes a super admin.

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-22 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "staff_users",
        sa.Column(
            "is_super_admin",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.execute("UPDATE staff_users SET is_super_admin = true WHERE is_platform_admin")
    op.create_check_constraint(
        op.f("ck_staff_users_super_admin_is_admin"),
        "staff_users",
        "NOT is_super_admin OR is_platform_admin",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_staff_users_super_admin_is_admin"), "staff_users", type_="check"
    )
    op.drop_column("staff_users", "is_super_admin")
