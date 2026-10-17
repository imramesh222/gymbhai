"""Web Push subscriptions: a member's phone that takes notifications (§16.3, 8.3)."""

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
