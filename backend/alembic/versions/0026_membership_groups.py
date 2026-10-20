"""Family and couple plans: one sale for several people (PLAN.md §19.1).

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-20 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column("seats", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.create_check_constraint(op.f("ck_plans_seats"), "plans", "seats BETWEEN 1 AND 6")
    op.create_check_constraint(
        op.f("ck_plans_seats_no_visits"), "plans", "seats = 1 OR visit_limit IS NULL"
    )

    op.create_table(
        "membership_groups",
        sa.Column("plan_id", sa.UUID(), nullable=True),
        sa.Column("payer_member_id", sa.UUID(), nullable=False),
        sa.Column("seats", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
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
        sa.Column("gym_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "seats BETWEEN 2 AND 6", name=op.f("ck_membership_groups_seats")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["staff_users.id"],
            name=op.f("fk_membership_groups_created_by_staff_users"),
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_membership_groups_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["payer_member_id"],
            ["members.id"],
            name=op.f("fk_membership_groups_payer_member_id_members"),
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["plans.id"], name=op.f("fk_membership_groups_plan_id_plans")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_membership_groups")),
    )
    op.create_index(
        op.f("ix_membership_groups_gym_id"),
        "membership_groups",
        ["gym_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_membership_groups_payer_member_id"),
        "membership_groups",
        ["payer_member_id"],
        unique=False,
    )

    op.add_column("memberships", sa.Column("group_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_memberships_group_id_membership_groups"),
        "memberships",
        "membership_groups",
        ["group_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_memberships_group_id"), "memberships", ["group_id"], unique=False
    )

    op.add_column(
        "payment_requests",
        sa.Column(
            "with_member_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("payment_requests", "with_member_ids")
    op.drop_index(op.f("ix_memberships_group_id"), table_name="memberships")
    op.drop_constraint(
        op.f("fk_memberships_group_id_membership_groups"),
        "memberships",
        type_="foreignkey",
    )
    op.drop_column("memberships", "group_id")
    op.drop_index(
        op.f("ix_membership_groups_payer_member_id"), table_name="membership_groups"
    )
    op.drop_index(op.f("ix_membership_groups_gym_id"), table_name="membership_groups")
    op.drop_table("membership_groups")
    op.drop_constraint(op.f("ck_plans_seats_no_visits"), "plans", type_="check")
    op.drop_constraint(op.f("ck_plans_seats"), "plans", type_="check")
    op.drop_column("plans", "seats")
