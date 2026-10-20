"""Members' app payments confirmed by the gym's own eSewa, Khalti or Fonepay
merchant account (PLAN.md §20.2): the keys on the account, each payment from
start to the request it became, and which wallet confirmed a request.

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-20 17:33:30.872846
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "online_payments",
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("plan_id", sa.UUID(), nullable=False),
        sa.Column("payment_method_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("test", sa.Boolean(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column(
            "with_member_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("order_id", sa.String(length=25), nullable=False),
        sa.Column("provider_ref", sa.String(length=64), nullable=True),
        sa.Column("transaction_ref", sa.String(length=64), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("checks", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("replaced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_request_id", sa.UUID(), nullable=True),
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
            ["gym_id"], ["gyms.id"], name=op.f("fk_online_payments_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["members.id"],
            name=op.f("fk_online_payments_member_id_members"),
        ),
        sa.ForeignKeyConstraint(
            ["payment_method_id"],
            ["gym_payment_methods.id"],
            name=op.f("fk_online_payments_payment_method_id_gym_payment_methods"),
        ),
        sa.ForeignKeyConstraint(
            ["payment_request_id"],
            ["payment_requests.id"],
            name=op.f("fk_online_payments_payment_request_id_payment_requests"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["plans.id"], name=op.f("fk_online_payments_plan_id_plans")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_online_payments")),
        sa.UniqueConstraint("order_id", name=op.f("uq_online_payments_order_id")),
    )
    op.create_index(
        op.f("ix_online_payments_gym_id"), "online_payments", ["gym_id"], unique=False
    )
    op.create_index(
        "ix_online_payments_member_status",
        "online_payments",
        ["member_id", "status"],
        unique=False,
    )
    op.add_column(
        "gym_payment_methods",
        sa.Column("gateway_merchant", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "gym_payment_methods", sa.Column("gateway_secret", sa.Text(), nullable=True)
    )
    op.add_column(
        "gym_payment_methods",
        sa.Column(
            "gateway_test",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "gym_payment_methods",
        sa.Column("gateway_ok_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "gym_payment_methods", sa.Column("gateway_error", sa.Text(), nullable=True)
    )
    op.add_column(
        "payment_requests",
        sa.Column("confirmed_by", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payment_requests", "confirmed_by")
    op.drop_column("gym_payment_methods", "gateway_error")
    op.drop_column("gym_payment_methods", "gateway_ok_at")
    op.drop_column("gym_payment_methods", "gateway_test")
    op.drop_column("gym_payment_methods", "gateway_secret")
    op.drop_column("gym_payment_methods", "gateway_merchant")
    op.drop_index("ix_online_payments_member_status", table_name="online_payments")
    op.drop_index(op.f("ix_online_payments_gym_id"), table_name="online_payments")
    op.drop_table("online_payments")
