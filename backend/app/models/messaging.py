"""SMS, credits, reminder rules and notices (PLAN.md §6, §9)."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GymOwned, IdMixin, TimestampMixin

# What an SMS was for.
SMS_OTP = "otp"
SMS_WELCOME = "welcome"
SMS_MEMBERSHIP = "membership"
SMS_REMINDER = "reminder"
SMS_NOTICE = "notice"
SMS_MANUAL = "manual"
SMS_PAYMENT = "payment"
# From GymBhai to the owner (subscription reminders): on us, like sign-in codes.
SMS_PLATFORM = "platform"
SMS_SUMMARY = "summary"
FREE_KINDS = (SMS_OTP, SMS_PLATFORM)

# Where it is.
SMS_QUEUED = "queued"
SMS_SENT = "sent"
SMS_FAILED = "failed"
# Not sent because the gym had no credit left. Sign-in codes never are (§5.7).
SMS_NO_CREDIT = "no_credit"


class SmsMessage(IdMixin, TimestampMixin, GymOwned, Base):
    __tablename__ = "sms_messages"
    __table_args__ = (Index("ix_sms_messages_gym_created", "gym_id", "created_at"),)

    member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), index=True
    )
    to: Mapped[str] = mapped_column(String(10))
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default=SMS_QUEUED)
    provider: Mapped[str | None] = mapped_column(String(16))
    provider_ref: Mapped[str | None] = mapped_column(String(64))
    segments: Mapped[int] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )


class SmsCreditLedger(IdMixin, TimestampMixin, GymOwned, Base):
    """Every top-up and every SMS sent. The balance is the latest balance_after."""

    __tablename__ = "sms_credit_ledger"
    __table_args__ = (
        Index("ix_sms_credit_ledger_gym_created", "gym_id", "created_at"),
    )

    change: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(120))
    balance_after: Mapped[int] = mapped_column(Integer)
    sms_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sms_messages.id", ondelete="SET NULL")
    )


class ReminderRule(IdMixin, TimestampMixin, GymOwned, Base):
    """Send `template` this many days from a membership's end (−7 is a week before)."""

    __tablename__ = "reminder_rules"
    __table_args__ = (UniqueConstraint("gym_id", "days_from_expiry"),)

    days_from_expiry: Mapped[int] = mapped_column(Integer)
    template: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )


class ReminderLog(IdMixin, TimestampMixin, GymOwned, Base):
    """Which rule has reminded which membership: never the same one twice (§9)."""

    __tablename__ = "reminder_log"
    __table_args__ = (UniqueConstraint("rule_id", "membership_id"),)

    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reminder_rules.id", ondelete="CASCADE")
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memberships.id", ondelete="CASCADE"), index=True
    )
    sms_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sms_messages.id", ondelete="SET NULL")
    )


class Notice(IdMixin, TimestampMixin, GymOwned, Base):
    __tablename__ = "notices"
    __table_args__ = (Index("ix_notices_gym_published", "gym_id", "published_at"),)

    # Null means every branch.
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id")
    )
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    send_sms: Mapped[bool] = mapped_column(Boolean, default=False)
    sms_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )


class ScheduledRun(IdMixin, TimestampMixin, Base):
    """A daily task that has been queued for a date. The unique pair makes
    'run once a day' hold however many workers are running."""

    __tablename__ = "scheduled_runs"
    __table_args__ = (UniqueConstraint("name", "run_on"),)

    name: Mapped[str] = mapped_column(String(64))
    run_on: Mapped[date] = mapped_column(Date)
