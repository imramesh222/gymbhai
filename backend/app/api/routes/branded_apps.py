"""A gym's own app in the stores (PLAN.md §20.3).

GET  /gym/app            what was asked for, and the prices
PUT  /gym/app            ask for it, or change it before we start
POST /gym/app/icon       its square icon
POST /gym/app/withdraw   before we start

GET   /admin/apps              every gym's (us)
PATCH /admin/apps/{id}         how far it has got, the stores' details
GET   /admin/apps/{id}/build   the build file (brand.json)
"""

import uuid

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require, require_platform_admin
from app.api.tenancy import StaffContext
from app.core.errors import AppError, not_found
from app.core.permissions import Permission
from app.db.session import get_db
from app.models.branded_app import BrandedApp
from app.models.gym import Gym
from app.models.staff import StaffUser
from app.schemas.branded_apps import (
    AdminBrandedAppRead,
    AdminBrandedAppUpdate,
    BrandedAppIn,
    BrandedAppRead,
)
from app.services import branded_apps as service
from app.services import storage

router = APIRouter(prefix="/gym/app", tags=["gym"])
admin_router = APIRouter(prefix="/admin/apps", tags=["platform admin"])

# Paying us for it is the gym's setup, as the subscription is.
SETUP = require(Permission.SETUP_GYM)
ADMIN = Depends(require_platform_admin)


def _read(db: Session, row: BrandedApp | None) -> BrandedAppRead:
    setup, monthly = service.prices(db)
    read = BrandedAppRead(
        offered=service.offered(db), setup_price=setup, monthly_price=monthly
    )
    if row is not None:
        read.status = row.status  # type: ignore[assignment]
        read.app_name = row.app_name
        read.color = row.color
        read.icon_url = storage.signed_url(row.icon_key)
        read.play_url = row.play_url
        read.app_store_url = row.app_store_url
        read.asked_at = row.asked_at
        read.live_at = row.live_at
        read.setup_paid = row.setup_paid_at is not None
    return read


def _gym(db: Session, ctx: StaffContext) -> Gym:
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    return gym


def _own(db: Session, ctx: StaffContext) -> BrandedApp:
    row = service.of_gym(db, ctx.gym_id)
    if row is None:
        raise not_found("You haven't asked for your own app.")
    return row


@router.get("", response_model=BrandedAppRead)
def get_app(
    db: Session = Depends(get_db), ctx: StaffContext = Depends(SETUP)
) -> BrandedAppRead:
    return _read(db, service.of_gym(db, ctx.gym_id))


@router.put("", response_model=BrandedAppRead)
def ask(
    payload: BrandedAppIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SETUP),
) -> BrandedAppRead:
    row = service.ask(
        db,
        ctx.staff,
        _gym(db, ctx),
        app_name=payload.app_name.strip(),
        color=payload.color.lower(),
        request=request,
    )
    db.commit()
    return _read(db, row)


@router.post("/icon", response_model=BrandedAppRead)
async def upload_icon(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SETUP),
) -> BrandedAppRead:
    row = _own(db, ctx)
    data = await file.read(storage.MAX_BYTES + 1)
    if len(data) > storage.MAX_BYTES:
        raise AppError(413, "file_too_large", "That file is too large.")
    service.set_icon(db, ctx.staff, row, data, request)
    db.commit()
    return _read(db, row)


@router.post("/withdraw", response_model=BrandedAppRead)
def withdraw(
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SETUP),
) -> BrandedAppRead:
    row = service.withdraw(db, ctx.staff, _own(db, ctx), request)
    db.commit()
    return _read(db, row)


# --- us -------------------------------------------------------------------------


def _admin_reads(db: Session, rows: list[BrandedApp]) -> list[AdminBrandedAppRead]:
    gyms = {
        g.id: g
        for g in db.scalars(select(Gym).where(Gym.id.in_({r.gym_id for r in rows})))
    }
    return [
        AdminBrandedAppRead(
            id=r.id,
            gym_id=r.gym_id,
            gym_name=gyms[r.gym_id].name,
            gym_slug=gyms[r.gym_id].slug,
            status=r.status,  # type: ignore[arg-type]
            app_name=r.app_name,
            color=r.color,
            icon_url=storage.signed_url(r.icon_key),
            android_package=r.android_package,
            ios_bundle_id=r.ios_bundle_id,
            expo_project_id=r.expo_project_id,
            play_url=r.play_url,
            app_store_url=r.app_store_url,
            notes=r.notes,
            asked_at=r.asked_at,
            building_at=r.building_at,
            live_at=r.live_at,
            stopped_at=r.stopped_at,
            setup_paid_at=r.setup_paid_at,
        )
        for r in rows
    ]


def _admin_row(db: Session, app_id: uuid.UUID) -> BrandedApp:
    row = db.get(BrandedApp, app_id)
    if row is None:
        raise not_found("No such app.")
    return row


@admin_router.get("", response_model=list[AdminBrandedAppRead])
def list_apps(
    db: Session = Depends(get_db), admin: StaffUser = ADMIN
) -> list[AdminBrandedAppRead]:
    rows = list(db.scalars(select(BrandedApp).order_by(BrandedApp.asked_at.desc())))
    return _admin_reads(db, rows)


@admin_router.patch("/{app_id}", response_model=AdminBrandedAppRead)
def update_app(
    app_id: uuid.UUID,
    payload: AdminBrandedAppUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: StaffUser = ADMIN,
) -> AdminBrandedAppRead:
    row = _admin_row(db, app_id)
    changes = payload.model_dump(exclude_unset=True)
    service.admin_update(db, admin, row, changes, request)
    db.commit()
    return _admin_reads(db, [row])[0]


@admin_router.get("/{app_id}/build")
def build_file(
    app_id: uuid.UUID, db: Session = Depends(get_db), admin: StaffUser = ADMIN
) -> dict:
    """For `node mobile/scripts/brand.mjs <file>` (docs/BRANDED_APPS.md)."""
    row = _admin_row(db, app_id)
    gym = db.get(Gym, row.gym_id)
    assert gym is not None
    return service.build_file(row, gym)
