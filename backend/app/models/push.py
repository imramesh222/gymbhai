"""Web Push subscriptions: a member's phone that takes notifications (§16.3,
8.3), and a staff member's phone or computer (§18.6)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GymOwned, IdMixin, TimestampMixin

KIND_WEB = "web"
KIND_EXPO = "expo"


class PushSubscription(IdMixin, TimestampMixin, GymOwned, Base):
    """One browser on one phone. A family sharing a phone has one each.

    `revoked_at` is set when the member turns reminders off, signs out, or the
    push service says the subscription is gone; it is never used again.
    """

    __tablename__ = "push_subscriptions"
    __table_args__ = (
        # Named: by the naming convention both would be ..._member_id.
        UniqueConstraint(
            "member_id", "endpoint", name="uq_push_subscriptions_member_id"
        ),
        UniqueConstraint(
            "member_id", "expo_token", name="uq_push_subscriptions_member_expo_token"
        ),
        CheckConstraint(
            "(kind = 'web' AND endpoint IS NOT NULL AND p256dh IS NOT NULL"
            " AND auth IS NOT NULL) OR (kind = 'expo' AND expo_token IS NOT NULL)",
            name="kind_fields",
        ),
    )

    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), index=True
    )
    # "web": the browser's Web Push (M8). "expo": the phone app (PLAN.md §17.6).
    kind: Mapped[str] = mapped_column(
        String(8), default=KIND_WEB, server_default=KIND_WEB
    )
    # Web Push.
    endpoint: Mapped[str | None] = mapped_column(Text)
    p256dh: Mapped[str | None] = mapped_column(String(200))
    auth: Mapped[str | None] = mapped_column(String(100))
    # The phone app: "ExponentPushToken[...]".
    expo_token: Mapped[str | None] = mapped_column(String(255))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StaffPushSubscription(IdMixin, TimestampMixin, Base):
    """One browser of one staff member, for notifications about what members
    did (PLAN.md §18.6). It belongs to the sign-in that turned it on: once
    that session is signed out or runs out, nothing is sent to it, so a lost
    phone stops showing members' names. Signing in again as the same person
    links it to the new session (`resume`).

    `revoked_at` is set when they turn it off, or the push service says it is
    gone; it is never used again.
    """

    __tablename__ = "staff_push_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "staff_user_id", "endpoint", name="uq_staff_push_subscriptions_staff"
        ),
    )

    staff_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id", ondelete="CASCADE"), index=True
    )
    # Null once the session is deleted (a week after it ends): not sent to.
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("staff_sessions.id", ondelete="SET NULL"),
        index=True,
    )
    endpoint: Mapped[str] = mapped_column(Text)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
