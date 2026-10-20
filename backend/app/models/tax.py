"""Tax invoices for VAT-registered gyms (PLAN.md §20.4).

Off on a server until GymBhai is certified by IRD (TAX_INVOICES_CERTIFIED).
An invoice is made with each payment once the gym turns VAT on, numbered in
its fiscal year, and never changed: a void or a refund issues a credit note
against it. What it says is copied when it's issued (the seller, the buyer,
the lines), so later changes to the gym or a plan change no invoice.
"""

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GymOwned, IdMixin, TimestampMixin

INVOICE = "invoice"
CREDIT_NOTE = "credit_note"

# Reporting to IRD's CBMS.
CBMS_OFF = "off"  # the gym doesn't report
CBMS_WAITING = "waiting"
CBMS_SENT = "sent"
CBMS_REFUSED = "refused"


class GymTax(IdMixin, TimestampMixin, GymOwned, Base):
    """A gym's VAT registration, and its CBMS account if it reports."""

    __tablename__ = "gym_tax"
    __table_args__ = (UniqueConstraint("gym_id"),)

    vat_registered: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    # Permanent Account Number: 9 digits.
    pan: Mapped[str | None] = mapped_column(String(9))
    # Payments from this day on get invoices; none before it.
    starts_on: Mapped[dt.date | None] = mapped_column(Date)
    cbms_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    cbms_username: Mapped[str | None] = mapped_column(String(100))
    # The password, encrypted (app/core/sealed.py).
    cbms_secret: Mapped[str | None] = mapped_column(Text)
    # CBMS's last refusal of the credentials, for Settings.
    cbms_error: Mapped[str | None] = mapped_column(Text)


class TaxInvoice(IdMixin, TimestampMixin, GymOwned, Base):
    """A tax invoice, or a credit note (sales return) against one."""

    __tablename__ = "tax_invoices"
    __table_args__ = (
        UniqueConstraint("gym_id", "kind", "fiscal_year", "number"),
        # One invoice per payment.
        Index(
            "uq_tax_invoices_payment",
            "payment_id",
            unique=True,
            postgresql_where=text("kind = 'invoice'"),
        ),
        Index("ix_tax_invoices_gym_issued", "gym_id", "issued_at"),
        CheckConstraint("total > 0", name="total"),
        CheckConstraint("taxable + vat = total", name="adds_up"),
    )

    kind: Mapped[str] = mapped_column(String(16), default=INVOICE)
    # The BS fiscal year, from 1 Shrawan: "2083/84".
    fiscal_year: Mapped[str] = mapped_column(String(7))
    number: Mapped[int] = mapped_column(Integer)
    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id")
    )
    # A credit note's invoice.
    ref_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tax_invoices.id")
    )
    # Copied when issued: {name, address, pan}.
    seller: Mapped[dict] = mapped_column(JSONB)
    buyer_name: Mapped[str] = mapped_column(String(120))
    buyer_address: Mapped[str | None] = mapped_column(String(255))
    buyer_pan: Mapped[str | None] = mapped_column(String(9))
    # [{description, quantity, rate, amount}], before VAT, in paisa.
    lines: Mapped[list] = mapped_column(JSONB)
    taxable: Mapped[int] = mapped_column(Integer)
    vat: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    issued_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    issued_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    # A credit note's reason.
    reason: Mapped[str | None] = mapped_column(Text)
    # Prints and downloads: the first is the original, the rest copies.
    prints: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    last_printed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    cbms_status: Mapped[str] = mapped_column(String(16), default=CBMS_OFF)
    cbms_sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    cbms_error: Mapped[str | None] = mapped_column(Text)
