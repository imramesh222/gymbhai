"""Enquiries (leads) and who referred whom (PLAN.md §16.4, 9.1, 9.2, 9.6).

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-17 16:25:32.719849
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=10), nullable=True),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("plan_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("follow_up_on", sa.Date(), nullable=True),
        sa.Column("lost_reason", sa.String(length=200), nullable=True),
        sa.Column("assigned_to", sa.UUID(), nullable=True),
        sa.Column("trial_on", sa.Date(), nullable=True),
        sa.Column("referred_by_id", sa.UUID(), nullable=True),
        sa.Column("member_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            ["assigned_to"],
            ["staff_users.id"],
            name=op.f("fk_leads_assigned_to_staff_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["branch_id"], ["branches.id"], name=op.f("fk_leads_branch_id_branches")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["staff_users.id"],
            name=op.f("fk_leads_created_by_staff_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_leads_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["members.id"],
            name=op.f("fk_leads_member_id_members"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name=op.f("fk_leads_plan_id_plans"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["referred_by_id"],
            ["members.id"],
            name=op.f("fk_leads_referred_by_id_members"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leads")),
    )
    op.create_index(
        "ix_leads_gym_follow_up", "leads", ["gym_id", "follow_up_on"], unique=False
    )
    op.create_index(op.f("ix_leads_gym_id"), "leads", ["gym_id"], unique=False)
    op.create_index("ix_leads_gym_phone", "leads", ["gym_id", "phone"], unique=False)
    op.create_index("ix_leads_gym_status", "leads", ["gym_id", "status"], unique=False)
    op.add_column("members", sa.Column("referred_by_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_members_referred_by_id_members"),
        "members",
        "members",
        ["referred_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_members_referred_by_id_members"), "members", type_="foreignkey"
    )
    op.drop_column("members", "referred_by_id")
    op.drop_index("ix_leads_gym_status", table_name="leads")
    op.drop_index("ix_leads_gym_phone", table_name="leads")
    op.drop_index(op.f("ix_leads_gym_id"), table_name="leads")
    op.drop_index("ix_leads_gym_follow_up", table_name="leads")
    op.drop_table("leads")
