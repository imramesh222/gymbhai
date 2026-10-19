"""Personal training: PT plans, packages sold, sessions, and their money
(PLAN.md §18.3).

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-19 15:07:19.549407
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pt_plans",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=True),
        sa.Column("duration_months", sa.Integer(), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
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
            "(kind = 'sessions') = (sessions IS NOT NULL)",
            name=op.f("ck_pt_plans_pack"),
        ),
        sa.CheckConstraint(
            "kind IN ('monthly', 'sessions')", name=op.f("ck_pt_plans_kind")
        ),
        sa.CheckConstraint(
            "(duration_months IS NULL) <> (duration_days IS NULL)",
            name=op.f("ck_pt_plans_one_duration"),
        ),
        sa.CheckConstraint(
            "duration_days IS NULL OR duration_days > 0", name=op.f("ck_pt_plans_days")
        ),
        sa.CheckConstraint(
            "duration_months IS NULL OR duration_months > 0",
            name=op.f("ck_pt_plans_months"),
        ),
        sa.CheckConstraint("price >= 0", name=op.f("ck_pt_plans_price")),
        sa.CheckConstraint(
            "sessions IS NULL OR sessions > 0", name=op.f("ck_pt_plans_sessions")
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_pt_plans_gym_id_gyms")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pt_plans")),
    )
    op.create_index(op.f("ix_pt_plans_gym_id"), "pt_plans", ["gym_id"], unique=False)
    op.create_table(
        "pt_packages",
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("plan_id", sa.UUID(), nullable=True),
        sa.Column("plan_name", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=True),
        sa.Column("trainer_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("discount", sa.Integer(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
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
            "(kind = 'sessions') = (sessions IS NOT NULL)",
            name=op.f("ck_pt_packages_pack"),
        ),
        sa.CheckConstraint(
            "kind IN ('monthly', 'sessions')", name=op.f("ck_pt_packages_kind")
        ),
        sa.CheckConstraint("end_date >= start_date", name=op.f("ck_pt_packages_dates")),
        sa.CheckConstraint(
            "price >= 0 AND discount >= 0 AND discount <= price",
            name=op.f("ck_pt_packages_money"),
        ),
        sa.CheckConstraint(
            "sessions IS NULL OR sessions > 0", name=op.f("ck_pt_packages_sessions")
        ),
        sa.ForeignKeyConstraint(
            ["branch_id"],
            ["branches.id"],
            name=op.f("fk_pt_packages_branch_id_branches"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["staff_users.id"],
            name=op.f("fk_pt_packages_created_by_staff_users"),
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_pt_packages_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["member_id"], ["members.id"], name=op.f("fk_pt_packages_member_id_members")
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["pt_plans.id"], name=op.f("fk_pt_packages_plan_id_pt_plans")
        ),
        sa.ForeignKeyConstraint(
            ["trainer_id"],
            ["staff_users.id"],
            name=op.f("fk_pt_packages_trainer_id_staff_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pt_packages")),
    )
    op.create_index(
        op.f("ix_pt_packages_branch_id"), "pt_packages", ["branch_id"], unique=False
    )
    op.create_index(
        "ix_pt_packages_gym_end", "pt_packages", ["gym_id", "end_date"], unique=False
    )
    op.create_index(
        op.f("ix_pt_packages_gym_id"), "pt_packages", ["gym_id"], unique=False
    )
    op.create_index(
        op.f("ix_pt_packages_member_id"), "pt_packages", ["member_id"], unique=False
    )
    op.create_index(
        "ix_pt_packages_trainer_end",
        "pt_packages",
        ["trainer_id", "end_date"],
        unique=False,
    )
    op.create_table(
        "pt_sessions",
        sa.Column("package_id", sa.UUID(), nullable=False),
        sa.Column("trained_on", sa.Date(), nullable=False),
        sa.Column("trainer_id", sa.UUID(), nullable=False),
        sa.Column("recorded_by", sa.UUID(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", sa.UUID(), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_pt_sessions_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["pt_packages.id"],
            name=op.f("fk_pt_sessions_package_id_pt_packages"),
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"],
            ["staff_users.id"],
            name=op.f("fk_pt_sessions_recorded_by_staff_users"),
        ),
        sa.ForeignKeyConstraint(
            ["trainer_id"],
            ["staff_users.id"],
            name=op.f("fk_pt_sessions_trainer_id_staff_users"),
        ),
        sa.ForeignKeyConstraint(
            ["voided_by"],
            ["staff_users.id"],
            name=op.f("fk_pt_sessions_voided_by_staff_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pt_sessions")),
    )
    op.create_index(
        op.f("ix_pt_sessions_gym_id"), "pt_sessions", ["gym_id"], unique=False
    )
    op.create_index(
        op.f("ix_pt_sessions_package_id"), "pt_sessions", ["package_id"], unique=False
    )
    op.add_column("payments", sa.Column("pt_package_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_payments_pt_package_id"), "payments", ["pt_package_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_payments_pt_package_id_pt_packages"),
        "payments",
        "pt_packages",
        ["pt_package_id"],
        ["id"],
    )
    # Money for a membership or for personal training, not both.
    op.create_check_constraint(
        op.f("ck_payments_one_purpose"),
        "payments",
        "membership_id IS NULL OR pt_package_id IS NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_payments_one_purpose"), "payments", type_="check")
    op.drop_constraint(
        op.f("fk_payments_pt_package_id_pt_packages"), "payments", type_="foreignkey"
    )
    op.drop_index(op.f("ix_payments_pt_package_id"), table_name="payments")
    op.drop_column("payments", "pt_package_id")
    op.drop_index(op.f("ix_pt_sessions_package_id"), table_name="pt_sessions")
    op.drop_index(op.f("ix_pt_sessions_gym_id"), table_name="pt_sessions")
    op.drop_table("pt_sessions")
    op.drop_index("ix_pt_packages_trainer_end", table_name="pt_packages")
    op.drop_index(op.f("ix_pt_packages_member_id"), table_name="pt_packages")
    op.drop_index(op.f("ix_pt_packages_gym_id"), table_name="pt_packages")
    op.drop_index("ix_pt_packages_gym_end", table_name="pt_packages")
    op.drop_index(op.f("ix_pt_packages_branch_id"), table_name="pt_packages")
    op.drop_table("pt_packages")
    op.drop_index(op.f("ix_pt_plans_gym_id"), table_name="pt_plans")
    op.drop_table("pt_plans")
