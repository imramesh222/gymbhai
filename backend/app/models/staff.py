"""People who sign in with a password: gym staff, owners and platform admins."""

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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class StaffUser(IdMixin, TimestampMixin, Base):
    __tablename__ = "staff_users"
    __table_args__ = (
        CheckConstraint("email IS NOT NULL OR phone IS NOT NULL", name="has_login"),
        # A platform admin belongs to no gym; everyone else belongs to one.
        CheckConstraint(
            "(is_platform_admin AND gym_id IS NULL AND NOT is_owner)"
            " OR (NOT is_platform_admin AND gym_id IS NOT NULL)",
            name="gym_or_platform",
        ),
        Index(
            "uq_staff_users_owner_per_gym",
            "gym_id",
            unique=True,
            postgresql_where=text("is_owner"),
        ),
    )

    # Null only for platform admins.
    gym_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gyms.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    # Unique across ALL staff of all gyms, so signing in never needs a gym
    # name. Email is stored lower-cased, phone normalised (app/core/phone.py).
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    phone: Mapped[str | None] = mapped_column(String(10), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    is_owner: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    is_platform_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    # Permission keys (app/core/permissions.py). Ignored for the owner, who
    # always has every permission.
    permissions: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Two-step sign-in (PLAN.md §16.1). The authenticator secret is derived
    # from this nonce and TOTP_KEY, never stored (app/core/totp.py). A nonce
    # without `totp_enabled_at` is a setup that was started and not finished.
    totp_nonce: Mapped[str | None] = mapped_column(String(32))
    totp_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The last 30-second step a code was accepted for: no code works twice.
    totp_last_step: Mapped[int | None] = mapped_column(Integer)
    # Their own language (§16.6); null follows the gym's.
    language: Mapped[str | None] = mapped_column(String(2))
    # When they last opened What's new (§16.5, 10.4): a dot until then.
    changelog_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Notifications they turned off (§18.6): the kinds in
    # app/services/push/staff.py. Stored as what's off, so a kind added later
    # starts on.
    muted_notifications: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )

    @property
    def two_step_enabled(self) -> bool:
        return self.totp_enabled_at is not None


class StaffBranchAccess(IdMixin, TimestampMixin, Base):
    """Branches a staff member may work in. No rows means every branch."""

    __tablename__ = "staff_branch_access"
    __table_args__ = (UniqueConstraint("staff_user_id", "branch_id"),)

    staff_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id", ondelete="CASCADE")
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), index=True
    )


class StaffSession(IdMixin, TimestampMixin, Base):
    """One signed-in device. Holds the hash of its current refresh token."""

    __tablename__ = "staff_sessions"

    staff_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id", ondelete="CASCADE"), index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # The token this one replaced, accepted for a few seconds after rotation:
    # two tabs refreshing at once must not sign each other out.
    previous_token_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoginAttempt(IdMixin, TimestampMixin, Base):
    """One staff sign-in try, kept for the limits on guessing (PLAN.md §16.1).

    Written for unknown accounts too, so the limits count guesses at which
    accounts exist. `at` is the real time rather than created_at: the database's
    now() is fixed for a whole transaction, and a failure must be able to sort
    after the success before it.
    """

    __tablename__ = "login_attempts"
    __table_args__ = (
        Index("ix_login_attempts_identifier_at", "identifier", "at"),
        Index("ix_login_attempts_ip_at", "ip", "at"),
    )

    # The email or phone typed, in the form accounts are stored in.
    identifier: Mapped[str] = mapped_column(String(254))
    ip: Mapped[str | None] = mapped_column(String(64))
    succeeded: Mapped[bool] = mapped_column(Boolean)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StaffPasswordReset(IdMixin, TimestampMixin, Base):
    """A "forgot password" code sent to a staff member (PLAN.md §16.1).

    Written even when nobody has that email or phone, without a code, so the
    limits on asking count guesses at which accounts exist. Only the latest
    row for an email or phone can be used.
    """

    __tablename__ = "staff_password_resets"
    __table_args__ = (
        Index(
            "ix_staff_password_resets_identifier_created", "identifier", "created_at"
        ),
        Index("ix_staff_password_resets_ip_created", "ip", "created_at"),
    )

    # Null when the email or phone typed belongs to no account.
    staff_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id", ondelete="CASCADE"), index=True
    )
    identifier: Mapped[str] = mapped_column(String(254))
    code_hash: Mapped[str | None] = mapped_column(String(64))
    # The real time, so the latest row sorts last even within one transaction.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))


class StaffRecoveryCode(IdMixin, TimestampMixin, Base):
    """A single-use code for signing in without the authenticator app."""

    __tablename__ = "staff_recovery_codes"

    staff_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
