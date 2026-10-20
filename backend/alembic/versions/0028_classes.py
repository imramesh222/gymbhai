"""Classes: types, the weekly timetable, each class and its bookings; the
classes a plan lets one book (PLAN.md §19.4).

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-20 10:27:08.650245
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "class_types",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("places", sa.Integer(), nullable=False),
        sa.Column("color", sa.String(length=16), nullable=False),
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
            "minutes BETWEEN 10 AND 300", name=op.f("ck_class_types_minutes")
        ),
        sa.CheckConstraint(
            "places BETWEEN 1 AND 500", name=op.f("ck_class_types_places")
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_class_types_gym_id_gyms")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_class_types")),
    )
    op.create_index(
        op.f("ix_class_types_gym_id"), "class_types", ["gym_id"], unique=False
    )
    op.create_table(
        "class_slots",
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("type_id", sa.UUID(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("starts", sa.String(length=5), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("places", sa.Integer(), nullable=False),
        sa.Column("instructor_id", sa.UUID(), nullable=True),
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
        sa.CheckConstraint(
            "minutes BETWEEN 10 AND 300", name=op.f("ck_class_slots_minutes")
        ),
        sa.CheckConstraint(
            "places BETWEEN 1 AND 500", name=op.f("ck_class_slots_places")
        ),
        sa.CheckConstraint(
            "weekday BETWEEN 0 AND 6", name=op.f("ck_class_slots_weekday")
        ),
        sa.ForeignKeyConstraint(
            ["branch_id"],
            ["branches.id"],
            name=op.f("fk_class_slots_branch_id_branches"),
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_class_slots_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["instructor_id"],
            ["staff_users.id"],
            name=op.f("fk_class_slots_instructor_id_staff_users"),
        ),
        sa.ForeignKeyConstraint(
            ["type_id"],
            ["class_types.id"],
            name=op.f("fk_class_slots_type_id_class_types"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_class_slots")),
    )
    op.create_index(
        op.f("ix_class_slots_branch_id"), "class_slots", ["branch_id"], unique=False
    )
    op.create_index(
        op.f("ix_class_slots_gym_id"), "class_slots", ["gym_id"], unique=False
    )
    op.create_table(
        "classes",
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("type_id", sa.UUID(), nullable=False),
        sa.Column("slot_id", sa.UUID(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("instructor_id", sa.UUID(), nullable=True),
        sa.Column("places", sa.Integer(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
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
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_classes_times")),
        sa.CheckConstraint("places BETWEEN 1 AND 500", name=op.f("ck_classes_places")),
        sa.ForeignKeyConstraint(
            ["branch_id"], ["branches.id"], name=op.f("fk_classes_branch_id_branches")
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_classes_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["instructor_id"],
            ["staff_users.id"],
            name=op.f("fk_classes_instructor_id_staff_users"),
        ),
        sa.ForeignKeyConstraint(
            ["slot_id"],
            ["class_slots.id"],
            name=op.f("fk_classes_slot_id_class_slots"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["type_id"], ["class_types.id"], name=op.f("fk_classes_type_id_class_types")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_classes")),
        sa.UniqueConstraint("slot_id", "starts_at", name="uq_classes_slot_start"),
    )
    op.create_index(
        op.f("ix_classes_branch_id"), "classes", ["branch_id"], unique=False
    )
    op.create_index(op.f("ix_classes_gym_id"), "classes", ["gym_id"], unique=False)
    op.create_index(
        "ix_classes_gym_starts", "classes", ["gym_id", "starts_at"], unique=False
    )
    op.create_table(
        "class_bookings",
        sa.Column("class_id", sa.UUID(), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("booked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "late", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("attended", sa.Boolean(), nullable=True),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("booked_by", sa.UUID(), nullable=True),
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
            "status IN ('booked', 'waitlist', 'cancelled')",
            name=op.f("ck_class_bookings_status"),
        ),
        sa.ForeignKeyConstraint(
            ["booked_by"],
            ["staff_users.id"],
            name=op.f("fk_class_bookings_booked_by_staff_users"),
        ),
        sa.ForeignKeyConstraint(
            ["class_id"],
            ["classes.id"],
            name=op.f("fk_class_bookings_class_id_classes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_class_bookings_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["members.id"],
            name=op.f("fk_class_bookings_member_id_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_class_bookings")),
    )
    op.create_index(
        op.f("ix_class_bookings_class_id"), "class_bookings", ["class_id"], unique=False
    )
    op.create_index(
        op.f("ix_class_bookings_gym_id"), "class_bookings", ["gym_id"], unique=False
    )
    op.create_index(
        op.f("ix_class_bookings_member_id"),
        "class_bookings",
        ["member_id"],
        unique=False,
    )
    op.create_index(
        "uq_class_bookings_member",
        "class_bookings",
        ["class_id", "member_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'cancelled'"),
    )
    op.add_column(
        "memberships",
        sa.Column(
            "classes",
            sa.String(length=8),
            server_default=sa.text("'all'"),
            nullable=False,
        ),
    )
    op.add_column(
        "memberships",
        sa.Column(
            "class_type_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.add_column(
        "plans",
        sa.Column(
            "classes",
            sa.String(length=8),
            server_default=sa.text("'all'"),
            nullable=False,
        ),
    )
    op.add_column(
        "plans",
        sa.Column(
            "class_type_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("plans", "class_type_ids")
    op.drop_column("plans", "classes")
    op.drop_column("memberships", "class_type_ids")
    op.drop_column("memberships", "classes")
    op.drop_index(
        "uq_class_bookings_member",
        table_name="class_bookings",
        postgresql_where=sa.text("status <> 'cancelled'"),
    )
    op.drop_index(op.f("ix_class_bookings_member_id"), table_name="class_bookings")
    op.drop_index(op.f("ix_class_bookings_gym_id"), table_name="class_bookings")
    op.drop_index(op.f("ix_class_bookings_class_id"), table_name="class_bookings")
    op.drop_table("class_bookings")
    op.drop_index("ix_classes_gym_starts", table_name="classes")
    op.drop_index(op.f("ix_classes_gym_id"), table_name="classes")
    op.drop_index(op.f("ix_classes_branch_id"), table_name="classes")
    op.drop_table("classes")
    op.drop_index(op.f("ix_class_slots_gym_id"), table_name="class_slots")
    op.drop_index(op.f("ix_class_slots_branch_id"), table_name="class_slots")
    op.drop_table("class_slots")
    op.drop_index(op.f("ix_class_types_gym_id"), table_name="class_types")
    op.drop_table("class_types")
