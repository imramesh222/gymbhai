"""A gym's own app in the stores (PLAN.md §20.3): what each gym asked for and
how far it has got, and the add-on's prices among our settings.

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-20 18:04:16.345343
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "branded_apps",
        sa.Column("app_name", sa.String(length=30), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("icon_key", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("android_package", sa.String(length=100), nullable=False),
        sa.Column("ios_bundle_id", sa.String(length=100), nullable=False),
        sa.Column("expo_project_id", sa.String(length=64), nullable=True),
        sa.Column("play_url", sa.String(length=300), nullable=True),
        sa.Column("app_store_url", sa.String(length=300), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("asked_by", sa.UUID(), nullable=True),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("building_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("live_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("setup_paid_at", sa.DateTime(timezone=True), nullable=True),
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
            ["asked_by"],
            ["staff_users.id"],
            name=op.f("fk_branded_apps_asked_by_staff_users"),
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_branded_apps_gym_id_gyms")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_branded_apps")),
        sa.UniqueConstraint("gym_id", name=op.f("uq_branded_apps_gym_id")),
    )
    op.create_index(
        op.f("ix_branded_apps_gym_id"), "branded_apps", ["gym_id"], unique=False
    )
    op.add_column(
        "platform_settings",
        sa.Column("branded_app_setup_price", sa.Integer(), nullable=True),
    )
    op.add_column(
        "platform_settings",
        sa.Column("branded_app_monthly_price", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("platform_settings", "branded_app_monthly_price")
    op.drop_column("platform_settings", "branded_app_setup_price")
    op.drop_index(op.f("ix_branded_apps_gym_id"), table_name="branded_apps")
    op.drop_table("branded_apps")
