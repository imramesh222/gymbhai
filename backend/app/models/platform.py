"""What gyms send us: subscription payments and SMS top-ups (PLAN.md §5.7),
and register imports (§7 Import / Export)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GymOwned, IdMixin, TimestampMixin

KIND_SUBSCRIPTION = "subscription"
KIND_SMS = "sms"


class SubscriptionPayment(IdMixin, TimestampMixin, GymOwned, Base):
    """An owner's "we've paid you", for a plan or for SMS credits."""

    __tablename__ = "subscription_payments"

    kind: Mapped[str] = mapped_column(String(16), default=KIND_SUBSCRIPTION)
    platform_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_plans.id")
    )
    months: Mapped[int | None] = mapped_column(Integer)
    sms_credits: Mapped[int | None] = mapped_column(Integer)
    # Paisa.
    amount: Mapped[int] = mapped_column(Integer)
    transaction_ref: Mapped[str | None] = mapped_column(String(64))
    screenshot_key: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reject_reason: Mapped[str | None] = mapped_column(Text)


class MemberImport(IdMixin, TimestampMixin, GymOwned, Base):
    """An uploaded register, parsed and waiting to be checked and committed."""

    __tablename__ = "member_imports"

    filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="preview")
    headers: Mapped[list[str]] = mapped_column(JSONB)
    rows: Mapped[list[list[Any]]] = mapped_column(JSONB)
    mapping: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
