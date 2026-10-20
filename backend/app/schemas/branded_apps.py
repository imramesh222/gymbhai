"""A gym's own app in the stores (PLAN.md §20.3)."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.auth import Strict

AppStatus = Literal["asked", "building", "in_review", "live", "stopped"]
COLOR = r"^#[0-9a-fA-F]{6}$"
HTTPS = r"^https://"


class BrandedAppIn(Strict):
    # As the stores show it, under the icon.
    app_name: str = Field(min_length=2, max_length=30)
    color: str = Field(pattern=COLOR)


class BrandedAppRead(BaseModel):
    """The gym's view: what they asked for, how far it is, what it costs."""

    offered: bool
    setup_price: int | None
    monthly_price: int | None
    status: AppStatus | None = None
    app_name: str | None = None
    color: str | None = None
    icon_url: str | None = None
    play_url: str | None = None
    app_store_url: str | None = None
    asked_at: dt.datetime | None = None
    live_at: dt.datetime | None = None
    setup_paid: bool = False


class AdminBrandedAppRead(BaseModel):
    id: uuid.UUID
    gym_id: uuid.UUID
    gym_name: str
    gym_slug: str
    status: AppStatus
    app_name: str
    color: str
    icon_url: str | None
    android_package: str
    ios_bundle_id: str
    expo_project_id: str | None
    play_url: str | None
    app_store_url: str | None
    notes: str | None
    asked_at: dt.datetime
    building_at: dt.datetime | None
    live_at: dt.datetime | None
    stopped_at: dt.datetime | None
    setup_paid_at: dt.datetime | None


class AdminBrandedAppUpdate(Strict):
    status: AppStatus | None = None
    app_name: str | None = Field(default=None, min_length=2, max_length=30)
    android_package: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$", max_length=100
    )
    ios_bundle_id: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$", max_length=100
    )
    expo_project_id: str | None = Field(default=None, max_length=64)
    play_url: str | None = Field(default=None, pattern=HTTPS, max_length=300)
    app_store_url: str | None = Field(default=None, pattern=HTTPS, max_length=300)
    notes: str | None = Field(default=None, max_length=2000)


class PublicApp(BaseModel):
    """A live app the member web app offers instead of GymBhai's."""

    name: str
    play_url: str | None
    app_store_url: str | None
