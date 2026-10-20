"""Fingerprint and face readers: devices of a brand, and who is on each
(PLAN.md §18.2).

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-20 00:46:47.693000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reader_users",
        sa.Column("device_id", sa.UUID(), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("pin", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=48), nullable=False),
        sa.Column("on_reader", sa.Boolean(), nullable=False),
        sa.Column("until", sa.Date(), nullable=True),
        sa.Column("command_id", sa.Integer(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("gym_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name=op.f("fk_reader_users_device_id_devices"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_reader_users_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["members.id"],
            name=op.f("fk_reader_users_member_id_members"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reader_users")),
        sa.UniqueConstraint("device_id", "member_id", name="uq_reader_users_member"),
        sa.UniqueConstraint("device_id", "pin", name="uq_reader_users_pin"),
    )
    op.create_index(
        op.f("ix_reader_users_device_id"), "reader_users", ["device_id"], unique=False
    )
    op.create_index(
        op.f("ix_reader_users_gym_id"), "reader_users", ["gym_id"], unique=False
    )
    op.create_index(
        op.f("ix_reader_users_member_id"), "reader_users", ["member_id"], unique=False
    )
    op.add_column(
        "devices",
        sa.Column("kind", sa.String(length=16), server_default="kiosk", nullable=False),
    )
    op.add_column("devices", sa.Column("serial", sa.String(length=64), nullable=True))
    op.add_column(
        "devices", sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "devices",
        sa.Column(
            "command_seq", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
    )
    op.create_unique_constraint(op.f("uq_devices_serial"), "devices", ["serial"])


def downgrade() -> None:
    op.drop_constraint(op.f("uq_devices_serial"), "devices", type_="unique")
    op.drop_column("devices", "command_seq")
    op.drop_column("devices", "synced_at")
    op.drop_column("devices", "serial")
    op.drop_column("devices", "kind")
    op.drop_index(op.f("ix_reader_users_member_id"), table_name="reader_users")
    op.drop_index(op.f("ix_reader_users_gym_id"), table_name="reader_users")
    op.drop_index(op.f("ix_reader_users_device_id"), table_name="reader_users")
    op.drop_table("reader_users")
