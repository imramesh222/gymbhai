"""Tax invoices for VAT-registered gyms (PLAN.md §20.4): the gym's VAT
registration and CBMS account, and its invoices and credit notes.

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-20 18:18:12.229020
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gym_tax",
        sa.Column(
            "vat_registered",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("pan", sa.String(length=9), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column(
            "cbms_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("cbms_username", sa.String(length=100), nullable=True),
        sa.Column("cbms_secret", sa.Text(), nullable=True),
        sa.Column("cbms_error", sa.Text(), nullable=True),
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
            ["gym_id"], ["gyms.id"], name=op.f("fk_gym_tax_gym_id_gyms")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gym_tax")),
        sa.UniqueConstraint("gym_id", name=op.f("uq_gym_tax_gym_id")),
    )
    op.create_index(op.f("ix_gym_tax_gym_id"), "gym_tax", ["gym_id"], unique=False)
    op.create_table(
        "tax_invoices",
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("fiscal_year", sa.String(length=7), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.UUID(), nullable=False),
        sa.Column("ref_invoice_id", sa.UUID(), nullable=True),
        sa.Column("seller", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("buyer_name", sa.String(length=120), nullable=False),
        sa.Column("buyer_address", sa.String(length=255), nullable=True),
        sa.Column("buyer_pan", sa.String(length=9), nullable=True),
        sa.Column("lines", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("taxable", sa.Integer(), nullable=False),
        sa.Column("vat", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issued_by", sa.UUID(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("prints", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_printed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cbms_status", sa.String(length=16), nullable=False),
        sa.Column("cbms_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cbms_error", sa.Text(), nullable=True),
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
            "taxable + vat = total", name=op.f("ck_tax_invoices_adds_up")
        ),
        sa.CheckConstraint("total > 0", name=op.f("ck_tax_invoices_total")),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name=op.f("fk_tax_invoices_gym_id_gyms")
        ),
        sa.ForeignKeyConstraint(
            ["issued_by"],
            ["staff_users.id"],
            name=op.f("fk_tax_invoices_issued_by_staff_users"),
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            name=op.f("fk_tax_invoices_payment_id_payments"),
        ),
        sa.ForeignKeyConstraint(
            ["ref_invoice_id"],
            ["tax_invoices.id"],
            name=op.f("fk_tax_invoices_ref_invoice_id_tax_invoices"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tax_invoices")),
        sa.UniqueConstraint(
            "gym_id",
            "kind",
            "fiscal_year",
            "number",
            name=op.f("uq_tax_invoices_gym_id"),
        ),
    )
    op.create_index(
        op.f("ix_tax_invoices_gym_id"), "tax_invoices", ["gym_id"], unique=False
    )
    op.create_index(
        "ix_tax_invoices_gym_issued",
        "tax_invoices",
        ["gym_id", "issued_at"],
        unique=False,
    )
    op.create_index(
        "uq_tax_invoices_payment",
        "tax_invoices",
        ["payment_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'invoice'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_tax_invoices_payment",
        table_name="tax_invoices",
        postgresql_where=sa.text("kind = 'invoice'"),
    )
    op.drop_index("ix_tax_invoices_gym_issued", table_name="tax_invoices")
    op.drop_index(op.f("ix_tax_invoices_gym_id"), table_name="tax_invoices")
    op.drop_table("tax_invoices")
    op.drop_index(op.f("ix_gym_tax_gym_id"), table_name="gym_tax")
    op.drop_table("gym_tax")
