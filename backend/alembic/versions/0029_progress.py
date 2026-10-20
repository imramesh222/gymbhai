"""Progress: weight and measurements over time, private photos, height
(PLAN.md §19.5).

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-20 12:13:39.865913
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "progress_entries",
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("measured_on", sa.Date(), nullable=False),
        sa.Column("weight_g", sa.Integer(), nullable=True),
        sa.Column("body_fat", sa.Integer(), nullable=True),
        sa.Column("chest_mm", sa.Integer(), nullable=True),
        sa.Column("waist_mm", sa.Integer(), nullable=True),
        sa.Column("hips_mm", sa.Integer(), nullable=True),
        sa.Column("arm_mm", sa.Integer(), nullable=True),
        sa.Column("thigh_mm", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.UUID(), nullable=True),
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
            "body_fat IS NULL OR body_fat BETWEEN 10 AND 700",
            name=op.f("ck_progress_entries_body_fat"),
        ),
        sa.CheckConstraint(
            "weight_g IS NULL OR weight_g BETWEEN 20000 AND 300000",
            name=op.f("ck_progress_entries_weight"),
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_progress_entries_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["members.id"],
            name=op.f("fk_progress_entries_member_id_members"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"],
            ["staff_users.id"],
            name=op.f("fk_progress_entries_recorded_by_staff_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_progress_entries")),
    )
    op.create_index(
        op.f("ix_progress_entries_gym_id"), "progress_entries", ["gym_id"], unique=False
    )
    op.create_index(
        "ix_progress_entries_member_on",
        "progress_entries",
        ["member_id", "measured_on"],
        unique=False,
    )
    op.create_table(
        "progress_photos",
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("taken_on", sa.Date(), nullable=False),
        sa.Column("pose", sa.String(length=8), nullable=False),
        sa.Column("photo_key", sa.String(length=255), nullable=False),
        sa.Column(
            "shared", sa.Boolean(), server_default=sa.text("false"), nullable=False
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
            "pose IN ('front', 'side', 'back')", name=op.f("ck_progress_photos_pose")
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_progress_photos_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["members.id"],
            name=op.f("fk_progress_photos_member_id_members"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_progress_photos")),
    )
    op.create_index(
        op.f("ix_progress_photos_gym_id"), "progress_photos", ["gym_id"], unique=False
    )
    op.create_index(
        op.f("ix_progress_photos_member_id"),
        "progress_photos",
        ["member_id"],
        unique=False,
    )
    op.add_column("members", sa.Column("height_mm", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("members", "height_mm")
    op.drop_index(op.f("ix_progress_photos_member_id"), table_name="progress_photos")
    op.drop_index(op.f("ix_progress_photos_gym_id"), table_name="progress_photos")
    op.drop_table("progress_photos")
    op.drop_index("ix_progress_entries_member_on", table_name="progress_entries")
    op.drop_index(op.f("ix_progress_entries_gym_id"), table_name="progress_entries")
    op.drop_table("progress_entries")
