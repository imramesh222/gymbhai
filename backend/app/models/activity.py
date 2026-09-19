"""The append-only record of who changed what (PLAN.md §5.6, §11)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin

ACTOR_STAFF = "staff"
ACTOR_MEMBER = "member"
ACTOR_DEVICE = "device"
ACTOR_SYSTEM = "system"


class ActivityLog(IdMixin, TimestampMixin, Base):
    __tablename__ = "activity_log"
    __table_args__ = (
        Index("ix_activity_log_entity", "gym_id", "entity", "entity_id"),
        Index("ix_activity_log_gym_at", "gym_id", "at"),
    )

    # Null for platform-level actions that belong to no gym.
    gym_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gyms.id")
    )
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # {"field": {"before": ..., "after": ...}} for edits; free-form otherwise.
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
