"""Signing in at the desk with a QR, no SMS code (PLAN.md §18.4).

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-19 13:57:54.365509
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "member_sign_in_links",
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
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
            ["created_by"],
            ["staff_users.id"],
            name=op.f("fk_member_sign_in_links_created_by_staff_users"),
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_member_sign_in_links_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["members.id"],
            name=op.f("fk_member_sign_in_links_member_id_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_member_sign_in_links")),
        sa.UniqueConstraint(
            "token_hash", name=op.f("uq_member_sign_in_links_token_hash")
        ),
    )
    op.create_index(
        op.f("ix_member_sign_in_links_gym_id"),
        "member_sign_in_links",
        ["gym_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_member_sign_in_links_member_id"),
        "member_sign_in_links",
        ["member_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_member_sign_in_links_member_id"), table_name="member_sign_in_links"
    )
    op.drop_index(
        op.f("ix_member_sign_in_links_gym_id"), table_name="member_sign_in_links"
    )
    op.drop_table("member_sign_in_links")
