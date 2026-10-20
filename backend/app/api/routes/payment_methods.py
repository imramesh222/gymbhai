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
from app.core.errors import AppError
from app.core.permissions import Permission
from app.db.session import get_db
from app.models.payment import GymPaymentMethod
from app.schemas.money import (
    GatewayIn,
    GatewayStatus,
    PaymentMethodCreate,
    PaymentMethodRead,
    PaymentMethodUpdate,
)
from app.services import activity, online_payments, storage

router = APIRouter(prefix="/payment-methods", tags=["payment methods"])

SETUP = require(Permission.SETUP_PAYMENT_METHODS)
FIELDS = ("kind", "label", "account_name", "account_number", "is_active", "sort_order")


def read(method: GymPaymentMethod, *, staff: bool = True) -> PaymentMethodRead:
    """Members see only whether the wallet confirms payments; staff also see
    the keys' state (never the keys)."""
    result = PaymentMethodRead.model_validate(method)
    result.qr_image_url = storage.signed_url(method.qr_image_key)
    result.online = online_payments.online(method)
    if staff and method.gateway_secret is not None:
        result.gateway = GatewayStatus(
            merchant=method.gateway_merchant,
            hint=online_payments.hint(method),
            test=method.gateway_test,
            ok_at=method.gateway_ok_at,
            error=method.gateway_error,
        )
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
    if method.kind != before["kind"] and method.gateway_secret is not None:
        # eSewa's keys mean nothing to a bank account.
        online_payments.clear_keys(method)
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


# What each wallet needs (§20.2): eSewa's merchant code and secret key;
# Khalti's secret key; Fonepay's merchant code, secret key, username, password.
NEEDS = {
    "esewa": ("merchant",),
    "khalti": (),
    "fonepay": ("merchant", "username", "password"),
}


@router.put("/{method_id}/gateway", response_model=PaymentMethodRead)
def set_gateway(
    method_id: uuid.UUID,
    payload: GatewayIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SETUP),
) -> PaymentMethodRead:
    """The keys the wallet gave the gym, so payments to this account are
    confirmed by the wallet itself. Kept encrypted; never sent back."""
    method = get_in_gym(
        db, GymPaymentMethod, method_id, ctx, message="No such account."
    )
    if not online_payments.available():
        raise AppError(
            409,
            "gateway_unavailable",
            "Payments confirmed by the wallet aren't available yet.",
        )
    if method.kind not in NEEDS:
        raise AppError(
            422,
            "gateway_kind",
            "Only eSewa, Khalti and Fonepay accounts can confirm payments.",
        )
    values = payload.model_dump()
    missing = [name for name in NEEDS[method.kind] if not (values[name] or "").strip()]
    if missing:
        raise AppError(
            422,
            "gateway_missing",
            "Fill in every key the wallet gave you.",
            missing=missing,
        )
    secret = {"secret_key": payload.secret_key.strip()}
    for name in ("username", "password"):
        if name in NEEDS[method.kind]:
            secret[name] = (values[name] or "").strip()
    had = method.gateway_secret is not None
    online_payments.set_keys(
        method,
        merchant=(payload.merchant or "").strip() or None
        if "merchant" in NEEDS[method.kind]
        else None,
        secret=secret,
        test=payload.test,
    )
    # Which account and whether test: never the keys themselves.
    activity.staff_action(
        db,
        ctx.staff,
        "payment_method.gateway_changed" if had else "payment_method.gateway_set",
        entity="payment_method",
        entity_id=method.id,
        changes={"merchant": method.gateway_merchant, "test": method.gateway_test},
        request=request,
    )
    db.commit()
    return read(method)


@router.delete("/{method_id}/gateway", response_model=PaymentMethodRead)
def remove_gateway(
    method_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SETUP),
) -> PaymentMethodRead:
    """Back to the member's word and the desk's check."""
    method = get_in_gym(
        db, GymPaymentMethod, method_id, ctx, message="No such account."
    )
    if method.gateway_secret is not None:
        online_payments.clear_keys(method)
        activity.staff_action(
            db,
            ctx.staff,
            "payment_method.gateway_removed",
            entity="payment_method",
            entity_id=method.id,
            request=request,
        )
    db.commit()
    return read(method)
