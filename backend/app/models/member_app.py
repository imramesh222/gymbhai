"""The member app, the door, and app payments (PLAN.md §4, §5.4, §5.5)."""

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
from sqlalchemy.dialects.postgresql import JSONB, UUID
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


class MemberSignInLink(IdMixin, TimestampMixin, GymOwned, Base):
    """Signing in at the desk (PLAN.md §18.4): the QR staff show on a member's
    profile. It works once, for a few minutes, and only the newest one for a
    member works. Only its hash is kept."""

    __tablename__ = "member_sign_in_links"

    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    # "web" (the refresh token in a cookie) or "app" (the phone app keeps it in
    # secure storage; PLAN.md §17.2).
    client: Mapped[str] = mapped_column(String(8), default="web", server_default="web")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# A kiosk (a phone or tablet scanning QR codes), or a fingerprint and face
# reader of either brand the pilot gyms have (PLAN.md §18.2).
DEVICE_KIOSK = "kiosk"
DEVICE_ZKTECO = "zkteco"
DEVICE_HIKVISION = "hikvision"
READERS = (DEVICE_ZKTECO, DEVICE_HIKVISION)


class Device(IdMixin, TimestampMixin, GymOwned, Base):
    """A registered door scanner: a kiosk, or a fingerprint and face reader.
    It can only check people in (§4.3)."""

    __tablename__ = "devices"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(
        String(16), default=DEVICE_KIOSK, server_default=DEVICE_KIOSK
    )
    # A reader's serial number: how a ZKTeco reader says who it is (ADMS).
    serial: Mapped[str | None] = mapped_column(String(64), unique=True)
    # For a reader: when what it should hold was last worked out, and the
    # number of the last command made for it.
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    command_seq: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )


# Check-in methods.
METHOD_APP_QR = "app_qr"
METHOD_CARD_QR = "card_qr"
METHOD_MANUAL = "manual"
# At a reader (§18.2): how the member proved who they were.
METHOD_FINGERPRINT = "fingerprint"
METHOD_FACE = "face"
METHOD_CARD = "card"
METHOD_PIN = "pin"

# Results. Every scan is recorded, allowed or not (§4.3).
ALLOWED = "allowed"
WARNED = "warned"
OVERRIDE = "override"
DUPLICATE = "duplicate"
DENIED_EXPIRED = "denied_expired"
DENIED_FROZEN = "denied_frozen"
DENIED_BRANCH = "denied_branch"
DENIED_DUES = "denied_dues"
# A visit pack with every visit used (§16.4, 9.3).
DENIED_VISITS_USED = "denied_visits_used"
# An off-peak plan, outside its hours (9.4).
DENIED_HOURS = "denied_hours"
LET_IN = (ALLOWED, WARNED, OVERRIDE)


class CheckIn(IdMixin, TimestampMixin, GymOwned, Base):
    __tablename__ = "check_ins"
    __table_args__ = (
        Index("ix_check_ins_gym_at", "gym_id", "at"),
        Index("ix_check_ins_member_at", "member_id", "at"),
        # A kiosk's offline scan sent twice is recorded once (§19.2).
        Index(
            "uq_check_ins_device_client",
            "device_id",
            "client_id",
            unique=True,
            postgresql_where=text("client_id IS NOT NULL"),
        ),
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
    result: Mapped[str] = mapped_column(String(24))
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id")
    )
    staff_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    note: Mapped[str | None] = mapped_column(Text)
    # Decided by a kiosk with no internet and sent later (§19.2): the result
    # is what it decided at the door, never decided again here.
    offline: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    client_id: Mapped[str | None] = mapped_column(String(64))


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
    # A family or couple plan renewed by its payer: the others it covers,
    # as member ids, worked out by the server when the request is made (§19.1).
    with_member_ids: Mapped[list | None] = mapped_column(JSONB)
    # The wallet itself confirmed the money: esewa, khalti or fonepay (§20.2).
    # Null: only the member's word, for the desk to check.
    confirmed_by: Mapped[str | None] = mapped_column(String(16))


ONLINE_STARTED = "started"
ONLINE_PAID = "paid"
ONLINE_FAILED = "failed"
ONLINE_EXPIRED = "expired"


class OnlinePayment(IdMixin, TimestampMixin, GymOwned, Base):
    """A payment through the gym's own eSewa, Khalti or Fonepay merchant
    account, from starting it to the payment request it became (§20.2).

    The money goes to the gym's account; this only remembers what we asked
    the wallet and what it answered."""

    __tablename__ = "online_payments"
    __table_args__ = (Index("ix_online_payments_member_status", "member_id", "status"),)

    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id")
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id")
    )
    payment_method_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gym_payment_methods.id")
    )
    # esewa, khalti, fonepay: the account's kind.
    provider: Mapped[str] = mapped_column(String(16))
    # The wallet's test system, not real money.
    test: Mapped[bool] = mapped_column(Boolean, default=False)
    # Paisa: worked out by the server, never the member.
    amount: Mapped[int] = mapped_column(Integer)
    with_member_ids: Mapped[list | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default=ONLINE_STARTED)
    # Ours, sent to the wallet: letters and digits (Fonepay takes 25 at most).
    order_id: Mapped[str] = mapped_column(String(25), unique=True)
    # The wallet's id for it, when it gives one (Khalti's pidx).
    provider_ref: Mapped[str | None] = mapped_column(String(64))
    # The wallet's transaction, once paid.
    transaction_ref: Mapped[str | None] = mapped_column(String(64))
    # What the wallet's start answered (the checkout's address and form, or
    # the QR), whether it began in the phone app, and the console's answer.
    details: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    checks: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The wallet's last trouble, if any.
    error: Mapped[str | None] = mapped_column(Text)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # The member started another before this one was paid: if this one is
    # paid after all, the desk decides.
    replaced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_requests.id", ondelete="SET NULL")
    )


class FreezeRequest(IdMixin, TimestampMixin, GymOwned, Base):
    """A member's "please freeze my membership" from the app (§16.3, 8.6).

    Approving it makes an ordinary freeze (`freeze_id`), exactly as at the desk.
    """

    __tablename__ = "freeze_requests"
    __table_args__ = (Index("ix_freeze_requests_gym_status", "gym_id", "status"),)

    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), index=True
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memberships.id", ondelete="CASCADE")
    )
    from_date: Mapped[date] = mapped_column(Date)
    to_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default=REQUEST_PENDING)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reject_reason: Mapped[str | None] = mapped_column(Text)
    freeze_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("membership_freezes.id", ondelete="SET NULL")
    )


class ReaderUser(IdMixin, TimestampMixin, GymOwned, Base):
    """A member as a fingerprint or face reader knows them (PLAN.md §18.2):
    their number there, and what GymBhai last told the reader. Fingerprints
    and faces stay on the reader; nothing of them is kept here.

    A change to send has `done_at` empty; `command_id` is the number it was
    sent under, which the reader's answer quotes.
    """

    __tablename__ = "reader_users"
    __table_args__ = (
        UniqueConstraint("device_id", "member_id", name="uq_reader_users_member"),
        UniqueConstraint("device_id", "pin", name="uq_reader_users_pin"),
    )

    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), index=True
    )
    # Their number on the reader: the digits of their member code.
    pin: Mapped[str] = mapped_column(String(24))
    name: Mapped[str] = mapped_column(String(48))
    # On the reader at all; and the last day it should let them in (none: not
    # now). Taken off only long after they stopped coming.
    on_reader: Mapped[bool] = mapped_column(Boolean, default=True)
    until: Mapped[date | None] = mapped_column(Date)
    command_id: Mapped[int | None] = mapped_column(Integer)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
