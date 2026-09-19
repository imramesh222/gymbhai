"""Sign-in codes, member sessions, devices, check-ins, payment requests.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-19 08:42:29.223400
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "otp_codes",
        sa.Column("channel", sa.String(length=8), nullable=False),
        sa.Column("destination", sa.String(length=254), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "attempts", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
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
            ["gym_id"], ["gyms.id"], name=op.f("fk_otp_codes_gym_id_gyms")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_otp_codes")),
    )
    op.create_index(
        "ix_otp_codes_destination_created",
        "otp_codes",
        ["destination", "created_at"],
        unique=False,
    )
    op.create_index(op.f("ix_otp_codes_gym_id"), "otp_codes", ["gym_id"], unique=False)
    op.create_index(
        "ix_otp_codes_ip_created", "otp_codes", ["ip", "created_at"], unique=False
    )
    op.create_table(
        "devices",
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["branch_id"], ["branches.id"], name=op.f("fk_devices_branch_id_branches")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["staff_users.id"],
            name=op.f("fk_devices_created_by_staff_users"),
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_devices_gym_id_gyms")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_devices")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_devices_token_hash")),
    )
    op.create_index(
        op.f("ix_devices_branch_id"), "devices", ["branch_id"], unique=False
    )
    op.create_index(op.f("ix_devices_gym_id"), "devices", ["gym_id"], unique=False)
    op.create_table(
        "member_sessions",
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_token_hash", sa.String(length=64), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("device_label", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
            ["member_id"],
            ["members.id"],
            name=op.f("fk_member_sessions_member_id_members"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_member_sessions")),
        sa.UniqueConstraint(
            "refresh_token_hash", name=op.f("uq_member_sessions_refresh_token_hash")
        ),
    )
    op.create_index(
        op.f("ix_member_sessions_member_id"),
        "member_sessions",
        ["member_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_member_sessions_previous_token_hash"),
        "member_sessions",
        ["previous_token_hash"],
        unique=False,
    )
    op.create_table(
        "check_ins",
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("membership_id", sa.UUID(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("device_id", sa.UUID(), nullable=True),
        sa.Column("staff_user_id", sa.UUID(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
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
            ["branch_id"], ["branches.id"], name=op.f("fk_check_ins_branch_id_branches")
        ),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name=op.f("fk_check_ins_device_id_devices")
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_check_ins_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["member_id"], ["members.id"], name=op.f("fk_check_ins_member_id_members")
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            ["memberships.id"],
            name=op.f("fk_check_ins_membership_id_memberships"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["staff_user_id"],
            ["staff_users.id"],
            name=op.f("fk_check_ins_staff_user_id_staff_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_check_ins")),
    )
    op.create_index("ix_check_ins_gym_at", "check_ins", ["gym_id", "at"], unique=False)
    op.create_index(op.f("ix_check_ins_gym_id"), "check_ins", ["gym_id"], unique=False)
    op.create_index(
        "ix_check_ins_member_at", "check_ins", ["member_id", "at"], unique=False
    )
    op.create_index(
        op.f("ix_check_ins_membership_id"), "check_ins", ["membership_id"], unique=False
    )
    op.create_table(
        "payment_requests",
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("plan_id", sa.UUID(), nullable=False),
        sa.Column("payment_method_id", sa.UUID(), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("transaction_ref", sa.String(length=64), nullable=True),
        sa.Column("screenshot_key", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("membership_id", sa.UUID(), nullable=True),
        sa.Column("payment_id", sa.UUID(), nullable=True),
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
            ["gym_id"], ["gyms.id"], name=op.f("fk_payment_requests_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["members.id"],
            name=op.f("fk_payment_requests_member_id_members"),
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            ["memberships.id"],
            name=op.f("fk_payment_requests_membership_id_memberships"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            name=op.f("fk_payment_requests_payment_id_payments"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["payment_method_id"],
            ["gym_payment_methods.id"],
            name=op.f("fk_payment_requests_payment_method_id_gym_payment_methods"),
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["plans.id"], name=op.f("fk_payment_requests_plan_id_plans")
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["staff_users.id"],
            name=op.f("fk_payment_requests_reviewed_by_staff_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_requests")),
    )
    op.create_index(
        op.f("ix_payment_requests_gym_id"), "payment_requests", ["gym_id"], unique=False
    )
    op.create_index(
        "ix_payment_requests_gym_status",
        "payment_requests",
        ["gym_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_requests_member_id"),
        "payment_requests",
        ["member_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_payment_requests_member_id"), table_name="payment_requests")
    op.drop_index("ix_payment_requests_gym_status", table_name="payment_requests")
    op.drop_index(op.f("ix_payment_requests_gym_id"), table_name="payment_requests")
    op.drop_table("payment_requests")
    op.drop_index(op.f("ix_check_ins_membership_id"), table_name="check_ins")
    op.drop_index("ix_check_ins_member_at", table_name="check_ins")
    op.drop_index(op.f("ix_check_ins_gym_id"), table_name="check_ins")
    op.drop_index("ix_check_ins_gym_at", table_name="check_ins")
    op.drop_table("check_ins")
    op.drop_index(
        op.f("ix_member_sessions_previous_token_hash"), table_name="member_sessions"
    )
    op.drop_index(op.f("ix_member_sessions_member_id"), table_name="member_sessions")
    op.drop_table("member_sessions")
    op.drop_index(op.f("ix_devices_gym_id"), table_name="devices")
    op.drop_index(op.f("ix_devices_branch_id"), table_name="devices")
    op.drop_table("devices")
    op.drop_index("ix_otp_codes_ip_created", table_name="otp_codes")
    op.drop_index(op.f("ix_otp_codes_gym_id"), table_name="otp_codes")
    op.drop_index("ix_otp_codes_destination_created", table_name="otp_codes")
    op.drop_table("otp_codes")
