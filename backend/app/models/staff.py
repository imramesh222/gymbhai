"""People who sign in with a password: gym staff, owners and platform admins."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
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
