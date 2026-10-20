"""A gym's own app in the stores (PLAN.md §20.3).

The same code as the GymBhai member app, built once for one gym, with its
name and icon and that gym fixed. The gym publishes it under its own Apple and
Google developer accounts (Apple's guideline 4.2.6); we build and upload it.
One row per gym: what they asked for, and how far it has got.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GymOwned, IdMixin, TimestampMixin

APP_ASKED = "asked"
APP_BUILDING = "building"
APP_IN_REVIEW = "in_review"
APP_LIVE = "live"
APP_STOPPED = "stopped"
APP_STATUSES = (APP_ASKED, APP_BUILDING, APP_IN_REVIEW, APP_LIVE, APP_STOPPED)
# The monthly add-on is owed from when we start building until it's stopped.
BILLED = (APP_BUILDING, APP_IN_REVIEW, APP_LIVE)


class BrandedApp(IdMixin, TimestampMixin, GymOwned, Base):
    __tablename__ = "branded_apps"
    __table_args__ = (UniqueConstraint("gym_id"),)

    # As the stores show it, under the icon: 30 characters at most.
    app_name: Mapped[str] = mapped_column(String(30))
    # #rrggbb: the splash screen, the Android icon's background, buttons.
    color: Mapped[str] = mapped_column(String(7))
    # A square PNG of at least 1024 pixels; a storage key.
    icon_key: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default=APP_ASKED)
    # The stores' identifiers, fixed once it's first built.
    android_package: Mapped[str] = mapped_column(String(100))
    ios_bundle_id: Mapped[str] = mapped_column(String(100))
    # The Expo project the builds and push tokens belong to.
    expo_project_id: Mapped[str | None] = mapped_column(String(64))
    play_url: Mapped[str | None] = mapped_column(String(300))
    app_store_url: Mapped[str | None] = mapped_column(String(300))
    # Ours, in /admin.
    notes: Mapped[str | None] = mapped_column(Text)
    asked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    building_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    live_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The one-time setup fee, once we've seen it paid.
    setup_paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
