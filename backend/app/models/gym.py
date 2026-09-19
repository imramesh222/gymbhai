"""Gyms (the tenants) and their branches."""

from typing import Any

from sqlalchemy import Boolean, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.gym_settings import GymSettings
from app.db.base import Base, GymOwned, IdMixin, TimestampMixin

GYM_ACTIVE = "active"
GYM_SUSPENDED = "suspended"


class Gym(IdMixin, TimestampMixin, Base):
    __tablename__ = "gyms"

    # app.gymbahi.com/<slug>; see app/core/slugs.py
    slug: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    # A storage key; see app/services/storage.py.
    logo_key: Mapped[str | None] = mapped_column(String(255))
    brand_color: Mapped[str | None] = mapped_column(String(7))
    phone: Mapped[str | None] = mapped_column(String(10))
    address: Mapped[str | None] = mapped_column(String(255))
    # Operator sender IDs are at most 11 characters.
    sms_sender_name: Mapped[str | None] = mapped_column(String(11))
    # A GymSettings, as JSON. Use .config to read it.
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        String(16), default=GYM_ACTIVE, server_default=GYM_ACTIVE
    )

    @property
    def config(self) -> GymSettings:
        return GymSettings.model_validate(self.settings)


class Branch(IdMixin, TimestampMixin, GymOwned, Base):
    __tablename__ = "branches"
    __table_args__ = (UniqueConstraint("gym_id", "name"),)

    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
