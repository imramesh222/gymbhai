"""The member app, the door, and app payments (PLAN.md §4, §5.4, §5.5)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GymOwned, IdMixin, TimestampMixin


class OtpCode(IdMixin, TimestampMixin, GymOwned, Base):
    """A 6-digit sign-in code, sent by SMS or email. Only its hash is kept."""

    __tablename__ = "otp_codes"
    __table_args__ = (
        Index("ix_otp_codes_destination_created", "destination", "created_at"),
        Index("ix_otp_codes_ip_created", "ip", "created_at"),
    )

    channel: Mapped[str] = mapped_column(String(8))  # sms, email
    destination: Mapped[str] = mapped_column(String(254))
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))


class MemberSession(IdMixin, TimestampMixin, Base):
    """A member signed in on one device."""

    __tablename__ = "member_sessions"

    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    previous_token_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    device_label: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Device(IdMixin, TimestampMixin, GymOwned, Base):
    """A registered door scanner (kiosk). It can only check people in (§4.3)."""

    __tablename__ = "devices"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )


# Check-in methods. Fingerprint and face readers are later sources (§4.3).
METHOD_APP_QR = "app_qr"
METHOD_CARD_QR = "card_qr"
METHOD_MANUAL = "manual"

# Results. Every scan is recorded, allowed or not (§4.3).
ALLOWED = "allowed"
WARNED = "warned"
OVERRIDE = "override"
DUPLICATE = "duplicate"
DENIED_EXPIRED = "denied_expired"
DENIED_FROZEN = "denied_frozen"
DENIED_BRANCH = "denied_branch"
DENIED_DUES = "denied_dues"
LET_IN = (ALLOWED, WARNED, OVERRIDE)


class CheckIn(IdMixin, TimestampMixin, GymOwned, Base):
    __tablename__ = "check_ins"
    __table_args__ = (
        Index("ix_check_ins_gym_at", "gym_id", "at"),
        Index("ix_check_ins_member_at", "member_id", "at"),
    )

    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id")
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id")
    )
    membership_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memberships.id", ondelete="SET NULL"),
        index=True,
    )
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    method: Mapped[str] = mapped_column(String(16))
    result: Mapped[str] = mapped_column(String(16))
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id")
    )
    staff_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    note: Mapped[str | None] = mapped_column(Text)


REQUEST_PENDING = "pending"
REQUEST_APPROVED = "approved"
REQUEST_REJECTED = "rejected"
REQUEST_WITHDRAWN = "withdrawn"


class PaymentRequest(IdMixin, TimestampMixin, GymOwned, Base):
    """A member's "I've paid" from the app, waiting for staff (§5.4)."""

    __tablename__ = "payment_requests"
    __table_args__ = (Index("ix_payment_requests_gym_status", "gym_id", "status"),)

    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), index=True
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id")
    )
    payment_method_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gym_payment_methods.id")
    )
    amount: Mapped[int] = mapped_column(Integer)
    transaction_ref: Mapped[str | None] = mapped_column(String(64))
    screenshot_key: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default=REQUEST_PENDING)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reject_reason: Mapped[str | None] = mapped_column(Text)
    membership_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memberships.id", ondelete="SET NULL")
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="SET NULL")
    )
