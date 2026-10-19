"""Expenses: money the gym spent (PLAN.md §18.1).

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-19 12:35:18.251763
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "expenses",
        sa.Column("branch_id", sa.UUID(), nullable=True),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("spent_on", sa.Date(), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("paid_to", sa.String(length=120), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
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
        sa.CheckConstraint("amount > 0", name=op.f("ck_expenses_amount")),
        sa.ForeignKeyConstraint(
            ["branch_id"], ["branches.id"], name=op.f("fk_expenses_branch_id_branches")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["staff_users.id"],
            name=op.f("fk_expenses_created_by_staff_users"),
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_expenses_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["voided_by"],
            ["staff_users.id"],
            name=op.f("fk_expenses_voided_by_staff_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_expenses")),
    )
    op.create_index(op.f("ix_expenses_gym_id"), "expenses", ["gym_id"], unique=False)
    op.create_index(
        "ix_expenses_gym_spent_on", "expenses", ["gym_id", "spent_on"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_expenses_gym_spent_on", table_name="expenses")
    op.drop_index(op.f("ix_expenses_gym_id"), table_name="expenses")
    op.drop_table("expenses")
