"""Web Push subscriptions: a member's phone that takes notifications (§16.3, 8.3)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GymOwned, IdMixin, TimestampMixin


class PushSubscription(IdMixin, TimestampMixin, GymOwned, Base):
    """One browser on one phone. A family sharing a phone has one each.

    `revoked_at` is set when the member turns reminders off, signs out, or the
    push service says the subscription is gone; it is never used again.
    """

    __tablename__ = "push_subscriptions"
    __table_args__ = (UniqueConstraint("member_id", "endpoint"),)

    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), index=True
    )
    endpoint: Mapped[str] = mapped_column(Text)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
