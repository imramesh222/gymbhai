"""Members, plans, memberships, freezes, payments, payment methods, counters.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-19 01:44:26.347200
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gym_counters",
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Integer(), server_default=sa.text("0"), nullable=False),
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
            ["gym_id"], ["gyms.id"], name=op.f("fk_gym_counters_gym_id_gyms")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gym_counters")),
        sa.UniqueConstraint("gym_id", "name", name=op.f("uq_gym_counters_gym_id")),
    )
    op.create_index(
        op.f("ix_gym_counters_gym_id"), "gym_counters", ["gym_id"], unique=False
    )
    op.create_table(
        "gym_payment_methods",
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("account_name", sa.String(length=120), nullable=True),
        sa.Column("account_number", sa.String(length=64), nullable=True),
        sa.Column("qr_image_key", sa.String(length=255), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_gym_payment_methods_gym_id_gyms")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gym_payment_methods")),
    )
    op.create_index(
        op.f("ix_gym_payment_methods_gym_id"),
        "gym_payment_methods",
        ["gym_id"],
        unique=False,
    )
    op.create_table(
        "plans",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("duration_months", sa.Integer(), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column(
            "admission_fee", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "all_branches", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
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
            "(duration_months IS NULL) <> (duration_days IS NULL)",
            name=op.f("ck_plans_one_duration"),
        ),
        sa.CheckConstraint("admission_fee >= 0", name=op.f("ck_plans_admission_fee")),
        sa.CheckConstraint(
            "duration_days IS NULL OR duration_days > 0", name=op.f("ck_plans_days")
        ),
        sa.CheckConstraint(
            "duration_months IS NULL OR duration_months > 0",
            name=op.f("ck_plans_months"),
        ),
        sa.CheckConstraint("price IS NULL OR price >= 0", name=op.f("ck_plans_price")),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_plans_gym_id_gyms")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plans")),
    )
    op.create_index(op.f("ix_plans_gym_id"), "plans", ["gym_id"], unique=False)
    op.create_table(
        "members",
        sa.Column("home_branch_id", sa.UUID(), nullable=False),
        sa.Column("member_code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=10), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("gender", sa.String(length=16), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("emergency_contact", sa.String(length=120), nullable=True),
        sa.Column("photo_key", sa.String(length=255), nullable=True),
        sa.Column("joined_on", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "app_access", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("qr_secret", sa.String(length=64), nullable=False),
        sa.Column(
            "qr_version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("card_token", sa.String(length=32), nullable=False),
        sa.Column(
            "is_archived", sa.Boolean(), server_default=sa.text("false"), nullable=False
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
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_members_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["home_branch_id"],
            ["branches.id"],
            name=op.f("fk_members_home_branch_id_branches"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_members")),
    )
    op.create_index(op.f("ix_members_gym_id"), "members", ["gym_id"], unique=False)
    op.create_index(
        "ix_members_gym_phone", "members", ["gym_id", "phone"], unique=False
    )
    op.create_index(
        op.f("ix_members_home_branch_id"), "members", ["home_branch_id"], unique=False
    )
    op.create_index(
        "uq_members_gym_card", "members", ["gym_id", "card_token"], unique=True
    )
    op.create_index(
        "uq_members_gym_code", "members", ["gym_id", "member_code"], unique=True
    )
    op.create_table(
        "plan_branches",
        sa.Column("plan_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
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
            ["branch_id"],
            ["branches.id"],
            name=op.f("fk_plan_branches_branch_id_branches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name=op.f("fk_plan_branches_plan_id_plans"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plan_branches")),
        sa.UniqueConstraint(
            "plan_id", "branch_id", name=op.f("uq_plan_branches_plan_id")
        ),
    )
    op.create_index(
        op.f("ix_plan_branches_branch_id"), "plan_branches", ["branch_id"], unique=False
    )
    op.create_table(
        "memberships",
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("plan_id", sa.UUID(), nullable=True),
        sa.Column("plan_name", sa.String(length=80), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("discount", sa.Integer(), nullable=False),
        sa.Column("admission_fee", sa.Integer(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
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
        sa.CheckConstraint("end_date >= start_date", name=op.f("ck_memberships_dates")),
        sa.CheckConstraint(
            "price >= 0 AND discount >= 0 AND admission_fee >= 0",
            name=op.f("ck_memberships_money"),
        ),
        sa.ForeignKeyConstraint(
            ["branch_id"],
            ["branches.id"],
            name=op.f("fk_memberships_branch_id_branches"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["staff_users.id"],
            name=op.f("fk_memberships_created_by_staff_users"),
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_memberships_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["member_id"], ["members.id"], name=op.f("fk_memberships_member_id_members")
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["plans.id"], name=op.f("fk_memberships_plan_id_plans")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memberships")),
    )
    op.create_index(
        op.f("ix_memberships_branch_id"), "memberships", ["branch_id"], unique=False
    )
    op.create_index(
        "ix_memberships_gym_end", "memberships", ["gym_id", "end_date"], unique=False
    )
    op.create_index(
        op.f("ix_memberships_gym_id"), "memberships", ["gym_id"], unique=False
    )
    op.create_index(
        "ix_memberships_member_end",
        "memberships",
        ["member_id", "end_date"],
        unique=False,
    )
    op.create_table(
        "membership_freezes",
        sa.Column("membership_id", sa.UUID(), nullable=False),
        sa.Column("from_date", sa.Date(), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
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
            "to_date >= from_date", name=op.f("ck_membership_freezes_dates")
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_membership_freezes_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            ["memberships.id"],
            name=op.f("fk_membership_freezes_membership_id_memberships"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_membership_freezes")),
    )
    op.create_index(
        op.f("ix_membership_freezes_gym_id"),
        "membership_freezes",
        ["gym_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_membership_freezes_membership_id"),
        "membership_freezes",
        ["membership_id"],
        unique=False,
    )
    op.create_table(
        "payments",
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("membership_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("transaction_ref", sa.String(length=64), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("receipt_no", sa.Integer(), nullable=False),
        sa.Column("received_by", sa.UUID(), nullable=True),
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
        sa.CheckConstraint("amount > 0", name=op.f("ck_payments_amount")),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_payments_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["member_id"], ["members.id"], name=op.f("fk_payments_member_id_members")
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            ["memberships.id"],
            name=op.f("fk_payments_membership_id_memberships"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["received_by"],
            ["staff_users.id"],
            name=op.f("fk_payments_received_by_staff_users"),
        ),
        sa.ForeignKeyConstraint(
            ["voided_by"],
            ["staff_users.id"],
            name=op.f("fk_payments_voided_by_staff_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
    )
    op.create_index(op.f("ix_payments_gym_id"), "payments", ["gym_id"], unique=False)
    op.create_index(
        "ix_payments_gym_paid_at", "payments", ["gym_id", "paid_at"], unique=False
    )
    op.create_index(
        op.f("ix_payments_member_id"), "payments", ["member_id"], unique=False
    )
    op.create_index(
        op.f("ix_payments_membership_id"), "payments", ["membership_id"], unique=False
    )
    op.create_index(
        "uq_payments_gym_receipt", "payments", ["gym_id", "receipt_no"], unique=True
    )
    op.create_index(
        "uq_payments_gym_ref",
        "payments",
        ["gym_id", "transaction_ref"],
        unique=True,
        postgresql_where=sa.text("transaction_ref IS NOT NULL"),
    )
    op.alter_column(
        "gyms", "logo_url", new_column_name="logo_key", type_=sa.String(length=255)
    )


def downgrade() -> None:
    op.alter_column(
        "gyms", "logo_key", new_column_name="logo_url", type_=sa.String(length=500)
    )
    op.drop_index(
        "uq_payments_gym_ref",
        table_name="payments",
        postgresql_where=sa.text("transaction_ref IS NOT NULL"),
    )
    op.drop_index("uq_payments_gym_receipt", table_name="payments")
    op.drop_index(op.f("ix_payments_membership_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_member_id"), table_name="payments")
    op.drop_index("ix_payments_gym_paid_at", table_name="payments")
    op.drop_index(op.f("ix_payments_gym_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_index(
        op.f("ix_membership_freezes_membership_id"), table_name="membership_freezes"
    )
    op.drop_index(op.f("ix_membership_freezes_gym_id"), table_name="membership_freezes")
    op.drop_table("membership_freezes")
    op.drop_index("ix_memberships_member_end", table_name="memberships")
    op.drop_index(op.f("ix_memberships_gym_id"), table_name="memberships")
    op.drop_index("ix_memberships_gym_end", table_name="memberships")
    op.drop_index(op.f("ix_memberships_branch_id"), table_name="memberships")
    op.drop_table("memberships")
    op.drop_index(op.f("ix_plan_branches_branch_id"), table_name="plan_branches")
    op.drop_table("plan_branches")
    op.drop_index("uq_members_gym_code", table_name="members")
    op.drop_index("uq_members_gym_card", table_name="members")
    op.drop_index(op.f("ix_members_home_branch_id"), table_name="members")
    op.drop_index("ix_members_gym_phone", table_name="members")
    op.drop_index(op.f("ix_members_gym_id"), table_name="members")
    op.drop_table("members")
    op.drop_index(op.f("ix_plans_gym_id"), table_name="plans")
    op.drop_table("plans")
    op.drop_index(
        op.f("ix_gym_payment_methods_gym_id"), table_name="gym_payment_methods"
    )
    op.drop_table("gym_payment_methods")
    op.drop_index(op.f("ix_gym_counters_gym_id"), table_name="gym_counters")
    op.drop_table("gym_counters")
