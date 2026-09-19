"""The gym's own payment accounts and QR images (PLAN.md §5.2).

Shown to members on the Renew screen and printed as a desk standee. These are
the gym's accounts: money goes to the gym, never through us.
"""

import uuid

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.tenancy import StaffContext, for_gym, get_in_gym
from app.core.permissions import Permission
from app.db.session import get_db
from app.models.payment import GymPaymentMethod
from app.schemas.money import (
    PaymentMethodCreate,
    PaymentMethodRead,
    PaymentMethodUpdate,
)
from app.services import activity, storage

router = APIRouter(prefix="/payment-methods", tags=["payment methods"])

SETUP = require(Permission.SETUP_PAYMENT_METHODS)
FIELDS = ("kind", "label", "account_name", "account_number", "is_active", "sort_order")


def read(method: GymPaymentMethod) -> PaymentMethodRead:
    result = PaymentMethodRead.model_validate(method)
    result.qr_image_url = storage.signed_url(method.qr_image_key)
    return result


@router.get("", response_model=list[PaymentMethodRead])
def list_methods(
    include_hidden: bool = False,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require()),
) -> list[PaymentMethodRead]:
    stmt = for_gym(select(GymPaymentMethod), GymPaymentMethod, ctx)
    if not include_hidden:
        stmt = stmt.where(GymPaymentMethod.is_active)
    rows = db.scalars(
        stmt.order_by(GymPaymentMethod.sort_order, GymPaymentMethod.created_at)
    )
    return [read(m) for m in rows]


@router.post("", response_model=PaymentMethodRead, status_code=status.HTTP_201_CREATED)
def create_method(
    payload: PaymentMethodCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SETUP),
) -> PaymentMethodRead:
    method = GymPaymentMethod(gym_id=ctx.gym_id, **payload.model_dump())
    db.add(method)
    db.flush()
    activity.staff_action(
        db,
        ctx.staff,
        "payment_method.created",
        entity="payment_method",
        entity_id=method.id,
        changes=payload.model_dump(),
        request=request,
    )
    db.commit()
    return read(method)


@router.patch("/{method_id}", response_model=PaymentMethodRead)
def update_method(
    method_id: uuid.UUID,
    payload: PaymentMethodUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SETUP),
) -> PaymentMethodRead:
    method = get_in_gym(
        db, GymPaymentMethod, method_id, ctx, message="No such account."
    )
    before = {name: getattr(method, name) for name in FIELDS}
    for name, value in payload.model_dump(exclude_unset=True).items():
        if value is None and name in ("kind", "label", "is_active", "sort_order"):
            continue
        setattr(method, name, value)
    diff = activity.diff(before, {name: getattr(method, name) for name in FIELDS})
    if diff:
        activity.staff_action(
            db,
            ctx.staff,
            "payment_method.updated",
            entity="payment_method",
            entity_id=method.id,
            changes=diff,
            request=request,
        )
    db.commit()
    return read(method)


@router.post("/{method_id}/qr", response_model=PaymentMethodRead)
async def upload_qr(
    method_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SETUP),
) -> PaymentMethodRead:
    method = get_in_gym(
        db, GymPaymentMethod, method_id, ctx, message="No such account."
    )
    data = await file.read(storage.MAX_BYTES + 1)
    key = storage.put(
        storage.new_key(ctx.gym_id, "payment-qr", storage.sniff_image(data)), data
    )
    old = method.qr_image_key
    method.qr_image_key = key
    activity.staff_action(
        db,
        ctx.staff,
        "payment_method.qr_uploaded",
        entity="payment_method",
        entity_id=method.id,
        changes={"qr_image_key": {"before": old, "after": key}},
        request=request,
    )
    db.commit()
    storage.delete(old)
    return read(method)
