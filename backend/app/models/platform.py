"""What gyms send us: subscription payments and SMS top-ups (PLAN.md §5.7),
register imports (§7 Import / Export); and ours: What's new and gym referrals
(§16.5)."""

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


class ChangelogEntry(IdMixin, TimestampMixin, Base):
    """What's new in GymBhai, written in /admin (§16.5, 10.4). Ours, not a gym's.

    A draft until `published_at`; staff see a dot until they've read the newest.
    """

    __tablename__ = "changelog_entries"

    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id", ondelete="SET NULL")
    )


# A gym that sent us another (§16.5, 10.5).
REFERRAL_PENDING = "pending"  # signed up; not paid yet
REFERRAL_READY = "ready"  # their first payment approved: reward both
REFERRAL_REWARDED = "rewarded"
REFERRAL_REJECTED = "rejected"


class GymReferral(IdMixin, TimestampMixin, GymOwned, Base):
    """`gym_id` sent us `referred_gym_id`. Each gym can be referred once."""

    __tablename__ = "gym_referrals"

    referred_gym_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gyms.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(String(16), default=REFERRAL_PENDING)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)
