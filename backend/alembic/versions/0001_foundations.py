"""Foundations: gyms, branches, staff, sessions, activity log, billing, jobs.

Revision ID: 0001
Revises:
Create Date: 2026-09-19 01:19:38.044246
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gyms",
        sa.Column("slug", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("logo_url", sa.String(length=500), nullable=True),
        sa.Column("brand_color", sa.String(length=7), nullable=True),
        sa.Column("phone", sa.String(length=10), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("sms_sender_name", sa.String(length=11), nullable=True),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="active", nullable=False
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gyms")),
        sa.UniqueConstraint("slug", name=op.f("uq_gyms_slug")),
    )
    op.create_table(
        "jobs",
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "run_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "attempts", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index(
        "ix_jobs_due",
        "jobs",
        ["run_at"],
        unique=False,
        postgresql_where=sa.text("done_at IS NULL"),
    )
    op.create_table(
        "platform_plans",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("max_active_members", sa.Integer(), nullable=True),
        sa.Column("max_branches", sa.Integer(), nullable=True),
        sa.Column("monthly_price", sa.Integer(), nullable=True),
        sa.Column(
            "included_sms", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_plans")),
    )
    op.create_table(
        "activity_log",
        sa.Column("gym_id", sa.UUID(), nullable=True),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
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
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_activity_log_gym_id_gyms")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_activity_log")),
    )
    op.create_index(
        "ix_activity_log_entity",
        "activity_log",
        ["gym_id", "entity", "entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_activity_log_gym_at", "activity_log", ["gym_id", "at"], unique=False
    )
    op.create_table(
        "branches",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=10), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
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
            ["gym_id"], ["gyms.id"], name=op.f("fk_branches_gym_id_gyms")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_branches")),
        sa.UniqueConstraint("gym_id", "name", name=op.f("uq_branches_gym_id")),
    )
    op.create_index(op.f("ix_branches_gym_id"), "branches", ["gym_id"], unique=False)
    op.create_table(
        "gym_subscriptions",
        sa.Column("platform_plan_id", sa.UUID(), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
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
            ["gym_id"], ["gyms.id"], name=op.f("fk_gym_subscriptions_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["platform_plan_id"],
            ["platform_plans.id"],
            name=op.f("fk_gym_subscriptions_platform_plan_id_platform_plans"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gym_subscriptions")),
    )
    op.create_index(
        op.f("ix_gym_subscriptions_gym_id"),
        "gym_subscriptions",
        ["gym_id"],
        unique=False,
    )
    op.create_table(
        "staff_users",
        sa.Column("gym_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("phone", sa.String(length=10), nullable=True),
        sa.Column("password_hash", sa.String(length=100), nullable=False),
        sa.Column(
            "is_owner", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "is_platform_admin",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "permissions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "(is_platform_admin AND gym_id IS NULL AND NOT is_owner) OR (NOT is_platform_admin AND gym_id IS NOT NULL)",
            name=op.f("ck_staff_users_gym_or_platform"),
        ),
        sa.CheckConstraint(
            "email IS NOT NULL OR phone IS NOT NULL",
            name=op.f("ck_staff_users_has_login"),
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_staff_users_gym_id_gyms")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_users")),
        sa.UniqueConstraint("email", name=op.f("uq_staff_users_email")),
        sa.UniqueConstraint("phone", name=op.f("uq_staff_users_phone")),
    )
    op.create_index(
        op.f("ix_staff_users_gym_id"), "staff_users", ["gym_id"], unique=False
    )
    op.create_index(
        "uq_staff_users_owner_per_gym",
        "staff_users",
        ["gym_id"],
        unique=True,
        postgresql_where=sa.text("is_owner"),
    )
    op.create_table(
        "staff_branch_access",
        sa.Column("staff_user_id", sa.UUID(), nullable=False),
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
            name=op.f("fk_staff_branch_access_branch_id_branches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["staff_user_id"],
            ["staff_users.id"],
            name=op.f("fk_staff_branch_access_staff_user_id_staff_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_branch_access")),
        sa.UniqueConstraint(
            "staff_user_id",
            "branch_id",
            name=op.f("uq_staff_branch_access_staff_user_id"),
        ),
    )
    op.create_index(
        op.f("ix_staff_branch_access_branch_id"),
        "staff_branch_access",
        ["branch_id"],
        unique=False,
    )
    op.create_table(
        "staff_sessions",
        sa.Column("staff_user_id", sa.UUID(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_token_hash", sa.String(length=64), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
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
            ["staff_user_id"],
            ["staff_users.id"],
            name=op.f("fk_staff_sessions_staff_user_id_staff_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_sessions")),
        sa.UniqueConstraint(
            "refresh_token_hash", name=op.f("uq_staff_sessions_refresh_token_hash")
        ),
    )
    op.create_index(
        op.f("ix_staff_sessions_previous_token_hash"),
        "staff_sessions",
        ["previous_token_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staff_sessions_staff_user_id"),
        "staff_sessions",
        ["staff_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_staff_sessions_staff_user_id"), table_name="staff_sessions")
    op.drop_index(
        op.f("ix_staff_sessions_previous_token_hash"), table_name="staff_sessions"
    )
    op.drop_table("staff_sessions")
    op.drop_index(
        op.f("ix_staff_branch_access_branch_id"), table_name="staff_branch_access"
    )
    op.drop_table("staff_branch_access")
    op.drop_index(
        "uq_staff_users_owner_per_gym",
        table_name="staff_users",
        postgresql_where=sa.text("is_owner"),
    )
    op.drop_index(op.f("ix_staff_users_gym_id"), table_name="staff_users")
    op.drop_table("staff_users")
    op.drop_index(op.f("ix_gym_subscriptions_gym_id"), table_name="gym_subscriptions")
    op.drop_table("gym_subscriptions")
    op.drop_index(op.f("ix_branches_gym_id"), table_name="branches")
    op.drop_table("branches")
    op.drop_index("ix_activity_log_gym_at", table_name="activity_log")
    op.drop_index("ix_activity_log_entity", table_name="activity_log")
    op.drop_table("activity_log")
    op.drop_table("platform_plans")
    op.drop_index(
        "ix_jobs_due", table_name="jobs", postgresql_where=sa.text("done_at IS NULL")
    )
    op.drop_table("jobs")
    op.drop_table("gyms")
