"""Money the gym received or gave back (PLAN.md §5.2, §6).

Money never passes through us: these rows record what happened at the desk or
in the gym's own wallet. Amounts are integer paisa. Payments are never
deleted, only voided with a reason.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GymOwned, IdMixin, TimestampMixin

KIND_PAYMENT = "payment"
KIND_REFUND = "refund"
METHODS = ("cash", "esewa", "khalti", "fonepay", "bank")
ACCOUNT_KINDS = ("esewa", "khalti", "fonepay", "bank", "other")


class Payment(IdMixin, TimestampMixin, GymOwned, Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount"),
        # One transaction ID pays for one thing, per gym (§5.4).
        Index(
            "uq_payments_gym_ref",
            "gym_id",
            "transaction_ref",
            unique=True,
            postgresql_where=text("transaction_ref IS NOT NULL"),
        ),
        Index("uq_payments_gym_receipt", "gym_id", "receipt_no", unique=True),
        Index("ix_payments_gym_paid_at", "gym_id", "paid_at"),
    )

    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), index=True
    )
    membership_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memberships.id", ondelete="SET NULL"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(16), default=KIND_PAYMENT)
    # Always positive; `kind` says which way the money went.
    amount: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(16))
    transaction_ref: Mapped[str | None] = mapped_column(String(64))
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    receipt_no: Mapped[int] = mapped_column(Integer)
    received_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    note: Mapped[str | None] = mapped_column(Text)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    void_reason: Mapped[str | None] = mapped_column(Text)


class GymPaymentMethod(IdMixin, TimestampMixin, GymOwned, Base):
    """The gym's own eSewa / Khalti / Fonepay / bank account, shown to members."""

    __tablename__ = "gym_payment_methods"

    kind: Mapped[str] = mapped_column(String(16))
    label: Mapped[str] = mapped_column(String(80))
    account_name: Mapped[str | None] = mapped_column(String(120))
    account_number: Mapped[str | None] = mapped_column(String(64))
    # A storage key; served through signed links.
    qr_image_key: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )


class GymCounter(IdMixin, TimestampMixin, GymOwned, Base):
    """Per-gym sequences (member codes, receipt numbers). See services/counters."""

    __tablename__ = "gym_counters"
    __table_args__ = (UniqueConstraint("gym_id", "name"),)

    name: Mapped[str] = mapped_column(String(32))
    value: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
