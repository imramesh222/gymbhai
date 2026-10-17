"""Answers to money requests, kept so a repeat gets the answer instead of a
second payment (PLAN.md §16.1, app/api/idempotency.py)."""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GymOwned, IdMixin, TimestampMixin


class IdempotencyKey(IdMixin, TimestampMixin, GymOwned, Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("gym_id", "key"),)

    # Made by the browser or the phone app, once per thing being saved.
    key: Mapped[str] = mapped_column(String(100))
    # A member's own action from the app (PLAN.md §17.4); null for staff. A
    # member's key only ever finds their own answers.
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE")
    )
    # "POST /api/v1/payments" and a hash of the body: the same key sent with a
    # different request is a mistake, not a repeat.
    route: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    # Written in the same transaction as the change itself, so a key is never
    # committed without its answer.
    status_code: Mapped[int | None] = mapped_column(Integer)
    response: Mapped[Any | None] = mapped_column(JSONB)
