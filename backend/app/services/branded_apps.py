"""A gym's own app in the stores (PLAN.md §20.3).

The gym asks from Settings, with a name, a colour and an icon; we build it
from the GymBhai app with that gym fixed, and the gym publishes it under its
own Apple and Google developer accounts (Apple's guideline 4.2.6). /admin
moves it along: asked, building, in review, live, stopped.
"""

import io
import re
import uuid
from typing import Any

from fastapi import Request
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.time import utcnow
from app.models.activity import ACTOR_STAFF
from app.models.billing import PlatformSettings
from app.models.branded_app import (
    APP_ASKED,
    APP_BUILDING,
    APP_LIVE,
    APP_STOPPED,
    BILLED,
    BrandedApp,
)
from app.models.gym import Gym
from app.models.staff import StaffUser
from app.services import activity, storage
from app.services.whatsapp.service import platform_settings

ICON_SIZE = 1024
FIELDS = (
    "app_name",
    "color",
    "status",
    "android_package",
    "ios_bundle_id",
    "expo_project_id",
    "play_url",
    "app_store_url",
    "notes",
)


def _snapshot(row: BrandedApp) -> dict[str, Any]:
    return {name: getattr(row, name) for name in FIELDS}


def prices(db: Session) -> tuple[int | None, int | None]:
    """(setup, monthly) in paisa; the add-on is offered only with both."""
    row: PlatformSettings = platform_settings(db)
    return row.branded_app_setup_price, row.branded_app_monthly_price


def offered(db: Session) -> bool:
    setup, monthly = prices(db)
    return setup is not None and monthly is not None


def of_gym(db: Session, gym_id: uuid.UUID) -> BrandedApp | None:
    return db.scalar(select(BrandedApp).where(BrandedApp.gym_id == gym_id))


def identifiers(slug: str) -> tuple[str, str]:
    """(Android package, iOS bundle id) to start with: np.gymbhai.<address>.
    A package's parts are letters, digits and _, starting with a letter."""
    part = re.sub(r"[^a-z0-9_]", "_", slug.lower())
    if not part[0].isalpha():
        part = f"g{part}"
    return f"np.gymbhai.{part}", f"np.gymbhai.{slug.lower()}"


def ask(
    db: Session,
    staff: StaffUser,
    gym: Gym,
    *,
    app_name: str,
    color: str,
    request: Request | None,
) -> BrandedApp:
    """Ask for the app, or change what was asked while we haven't started."""
    if not offered(db):
        raise AppError(409, "app_not_offered", "Your own app isn't offered yet.")
    row = of_gym(db, gym.id)
    if row is not None and row.status not in (APP_ASKED, APP_STOPPED):
        raise AppError(
            409,
            "app_started",
            "We've started building your app: ask us to change anything.",
        )
    before = _snapshot(row) if row else None
    if row is None:
        package, bundle = identifiers(gym.slug)
        row = BrandedApp(
            gym_id=gym.id,
            app_name=app_name,
            color=color,
            android_package=package,
            ios_bundle_id=bundle,
            asked_by=staff.id,
            asked_at=utcnow(),
        )
        db.add(row)
    else:
        row.app_name, row.color = app_name, color
        if row.status == APP_STOPPED:
            row.asked_by, row.asked_at, row.stopped_at = staff.id, utcnow(), None
    row.status = APP_ASKED
    db.flush()
    activity.staff_action(
        db,
        staff,
        "branded_app.asked",
        entity="branded_app",
        entity_id=row.id,
        changes=activity.diff(before, _snapshot(row)) if before else _snapshot(row),
        request=request,
    )
    return row


def withdraw(
    db: Session, staff: StaffUser, row: BrandedApp, request: Request | None
) -> BrandedApp:
    if row.status != APP_ASKED:
        raise AppError(
            409, "app_started", "We've started building your app: ask us to stop it."
        )
    row.status = APP_STOPPED
    row.stopped_at = utcnow()
    activity.staff_action(
        db,
        staff,
        "branded_app.withdrawn",
        entity="branded_app",
        entity_id=row.id,
        request=request,
    )
    return row


def set_icon(
    db: Session, staff: StaffUser, row: BrandedApp, data: bytes, request: Request | None
) -> BrandedApp:
    """A square PNG or JPEG of at least 1024 pixels, kept as a 1024 PNG with
    no transparency (the App Store refuses an icon with any)."""
    if row.status not in (APP_ASKED, APP_STOPPED):
        raise AppError(
            409, "app_started", "We've started building your app: send us the icon."
        )
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise AppError(422, "bad_icon", "That isn't an image.") from exc
    if image.width != image.height or image.width < ICON_SIZE:
        raise AppError(
            422,
            "bad_icon",
            f"The icon must be square, at least {ICON_SIZE} × {ICON_SIZE} pixels.",
            width=image.width,
            height=image.height,
        )
    flat = Image.new("RGB", image.size, row.color)
    rgba = image.convert("RGBA")
    flat.paste(rgba, mask=rgba.getchannel("A"))
    out = io.BytesIO()
    flat.resize((ICON_SIZE, ICON_SIZE), Image.Resampling.LANCZOS).save(out, "PNG")
    key = storage.put(storage.new_key(row.gym_id, "app-icon", "png"), out.getvalue())
    old, row.icon_key = row.icon_key, key
    activity.staff_action(
        db,
        staff,
        "branded_app.icon_changed",
        entity="branded_app",
        entity_id=row.id,
        changes={"icon_key": {"before": old, "after": key}},
        request=request,
    )
    storage.delete(old)
    return row


def admin_update(
    db: Session,
    admin: StaffUser,
    row: BrandedApp,
    changes: dict[str, Any],
    request: Request | None,
) -> BrandedApp:
    """Ours, from /admin: how far it has got, and the stores' details."""
    before = _snapshot(row)
    if row.building_at is not None and any(
        name in changes and changes[name] != getattr(row, name)
        for name in ("android_package", "ios_bundle_id")
    ):
        raise AppError(
            409,
            "app_ids_fixed",
            "The stores fix the package and bundle id once the app is built.",
        )
    for name, value in changes.items():
        setattr(row, name, value)
    now = utcnow()
    if "status" in changes and changes["status"] != before["status"]:
        if row.status == APP_BUILDING and row.building_at is None:
            row.building_at = now
        if row.status == APP_LIVE:
            row.live_at = row.live_at or now
            row.stopped_at = None
        if row.status == APP_STOPPED:
            row.stopped_at = now
    diff = activity.diff(before, _snapshot(row))
    if diff:
        activity.record(
            db,
            gym_id=row.gym_id,
            actor_type=ACTOR_STAFF,  # a platform admin, as /admin logs them
            actor_id=admin.id,
            action="branded_app.updated",
            entity="branded_app",
            entity_id=row.id,
            changes=diff,
            request=request,
        )
    return row


def build_file(row: BrandedApp, gym: Gym) -> dict[str, Any]:
    """What `mobile/scripts/brand.mjs` turns into a brand to build
    (mobile/brands/<address>/brand.json)."""
    return {
        "gym": gym.slug,
        "name": row.app_name,
        "color": row.color,
        "android_package": row.android_package,
        "ios_bundle_id": row.ios_bundle_id,
        "scheme": f"gb-{gym.slug}",
        "expo_project_id": row.expo_project_id,
        "api_url": settings.public_app_url,
        "icon_url": storage.signed_url(row.icon_key),
    }


def monthly_due(db: Session, gym_id: uuid.UUID) -> int | None:
    """The add-on's monthly price, while we build it and it's live."""
    row = of_gym(db, gym_id)
    if row is None or row.status not in BILLED:
        return None
    return prices(db)[1]


def setup_due(db: Session, gym_id: uuid.UUID) -> int | None:
    """The one-time fee, until it's been paid."""
    row = of_gym(db, gym_id)
    if row is None or row.status == APP_STOPPED or row.setup_paid_at is not None:
        return None
    return prices(db)[0]


def live(db: Session, gym_id: uuid.UUID) -> BrandedApp | None:
    row = of_gym(db, gym_id)
    return row if row is not None and row.status == APP_LIVE else None
