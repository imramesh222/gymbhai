"""Payments the gym recorded (PLAN.md §5.2, §5.6, §7).

Payments are never deleted, only voided with a reason, and every edit is logged.
"""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.presenters import payment_read, payments_read, staff_names
from app.api.tenancy import StaffContext, get_in_gym
from app.core.errors import AppError
from app.core.permissions import Permission
from app.core.time import NEPAL, utcnow
from app.db.session import get_db
from app.models.gym import Branch, Gym
from app.models.member import Member
from app.models.membership import Membership
from app.models.payment import KIND_PAYMENT, KIND_REFUND, Payment
from app.schemas.money import (
    PaymentCollect,
    PaymentList,
    PaymentListItem,
    PaymentRead,
    PaymentUpdate,
    Receipt,
    RefundCollect,
    VoidIn,
)
from app.services import activity
from app.services import memberships as ms

router = APIRouter(prefix="/payments", tags=["payments"])

FIELDS = ("amount", "method", "transaction_ref", "paid_at", "note")


def _membership(db: Session, ctx: StaffContext, membership_id: uuid.UUID) -> Membership:
    return get_in_gym(
        db,
        Membership,
        membership_id,
        ctx,
        branch_column=Membership.branch_id,
        message="No such membership.",
    )


def _payment(db: Session, ctx: StaffContext, payment_id: uuid.UUID) -> Payment:
    return get_in_gym(db, Payment, payment_id, ctx, message="No such payment.")


@router.post("", response_model=PaymentRead, status_code=status.HTTP_201_CREATED)
def collect(
    payload: PaymentCollect,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.PAYMENTS_COLLECT)),
) -> PaymentRead:
    """Money towards a membership: part payments of dues are normal (§6)."""
    membership = _membership(db, ctx, payload.membership_id)
    payment = ms.record_payment(
        db,
        ctx,
        membership,
        ms.PaymentIn(**payload.model_dump(exclude={"membership_id"})),
        request=request,
    )
    db.commit()
    return payment_read(payment, {ctx.staff.id: ctx.staff.name})


@router.post(
    "/refunds", response_model=PaymentRead, status_code=status.HTTP_201_CREATED
)
def refund(
    payload: RefundCollect,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.PAYMENTS_REFUND)),
) -> PaymentRead:
    membership = _membership(db, ctx, payload.membership_id)
    payment = ms.record_payment(
        db,
        ctx,
        membership,
        ms.PaymentIn(**payload.model_dump(exclude={"membership_id"})),
        kind=KIND_REFUND,
        request=request,
    )
    db.commit()
    return payment_read(payment, {ctx.staff.id: ctx.staff.name})


@router.get("", response_model=PaymentList)
def list_payments(
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.REPORTS_MONEY)),
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    method: str | None = None,
    received_by: uuid.UUID | None = None,
    include_voided: bool = True,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaymentList:
    """All payments; the totals are what the till should hold (§7)."""
    conditions = [Payment.gym_id == ctx.gym_id]
    # Days are Nepal days: "today's cash" must not end at 05:45 in the morning.
    if date_from:
        conditions.append(
            Payment.paid_at >= dt.datetime.combine(date_from, dt.time(), tzinfo=NEPAL)
        )
    if date_to:
        conditions.append(
            Payment.paid_at
            < dt.datetime.combine(
                date_to + dt.timedelta(days=1), dt.time(), tzinfo=NEPAL
            )
        )
    if method:
        conditions.append(Payment.method == method)
    if received_by:
        conditions.append(Payment.received_by == received_by)
    if ctx.branch_ids is not None:
        conditions.append(
            Payment.membership_id.in_(
                select(Membership.id).where(Membership.branch_id.in_(ctx.branch_ids))
            )
        )
    listed = list(conditions)
    if not include_voided:
        listed.append(Payment.voided_at.is_(None))

    total = db.scalar(select(func.count()).select_from(Payment).where(*listed)) or 0
    signed = case((Payment.kind == KIND_PAYMENT, Payment.amount), else_=-Payment.amount)
    live = [*conditions, Payment.voided_at.is_(None)]
    sum_amount = db.scalar(select(func.coalesce(func.sum(signed), 0)).where(*live)) or 0
    by_method = dict(
        db.execute(
            select(Payment.method, func.sum(signed))
            .where(*live)
            .group_by(Payment.method)
        ).all()
    )

    rows = db.execute(
        select(Payment, Member.name, Member.member_code)
        .join(Member, Member.id == Payment.member_id)
        .where(*listed)
        .order_by(Payment.paid_at.desc(), Payment.receipt_no.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    names = staff_names(db, [p.received_by for p, _, _ in rows])
    items = [
        PaymentListItem(
            **payment_read(p, names).model_dump(), member_name=name, member_code=code
        )
        for p, name, code in rows
    ]
    return PaymentList(
        items=items, total=total, sum_amount=sum_amount, by_method=by_method
    )


@router.patch("/{payment_id}", response_model=PaymentRead)
def update_payment(
    payment_id: uuid.UUID,
    payload: PaymentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.PAYMENTS_EDIT)),
) -> PaymentRead:
    """Correct the amount, method, date or transaction ID (§5.6)."""
    payment = _payment(db, ctx, payment_id)
    if payment.voided_at is not None:
        raise AppError(409, "payment_voided", "This payment has been voided.")
    before = {name: getattr(payment, name) for name in FIELDS}
    changes = payload.model_dump(exclude_unset=True, exclude={"reason"})
    for name, value in changes.items():
        if value is None and name in ("amount", "method", "paid_at"):
            continue
        if name == "transaction_ref":
            value = (value or "").strip() or None
            if value and db.scalar(
                select(Payment.id).where(
                    Payment.gym_id == ctx.gym_id,
                    Payment.transaction_ref == value,
                    Payment.id != payment.id,
                )
            ):
                raise AppError(
                    409,
                    "transaction_ref_used",
                    "That transaction ID has already been used.",
                )
        setattr(payment, name, value)
    diff = activity.diff(before, {name: getattr(payment, name) for name in FIELDS})
    if diff:
        activity.staff_action(
            db,
            ctx.staff,
            "payment.updated",
            entity="payment",
            entity_id=payment.id,
            changes={**diff, "membership_id": payment.membership_id},
            reason=payload.reason,
            request=request,
        )
    db.commit()
    return payments_read(db, [payment])[0]


@router.post("/{payment_id}/void", response_model=PaymentRead)
def void_payment(
    payment_id: uuid.UUID,
    payload: VoidIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.PAYMENTS_VOID)),
) -> PaymentRead:
    payment = _payment(db, ctx, payment_id)
    if payment.voided_at is not None:
        raise AppError(409, "payment_voided", "This payment has already been voided.")
    payment.voided_at = utcnow()
    payment.voided_by = ctx.staff.id
    payment.void_reason = payload.reason
    activity.staff_action(
        db,
        ctx.staff,
        "payment.voided",
        entity="payment",
        entity_id=payment.id,
        changes={"amount": payment.amount, "membership_id": payment.membership_id},
        reason=payload.reason,
        request=request,
    )
    db.commit()
    return payments_read(db, [payment])[0]


@router.get("/{payment_id}/receipt", response_model=Receipt)
def receipt(
    payment_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_VIEW)),
) -> Receipt:
    """A payment receipt, not a VAT invoice (§10)."""
    payment = _payment(db, ctx, payment_id)
    gym = db.get(Gym, ctx.gym_id)
    member = db.get(Member, payment.member_id)
    assert gym is not None and member is not None
    membership = (
        db.get(Membership, payment.membership_id) if payment.membership_id else None
    )
    branch = db.get(Branch, membership.branch_id) if membership else None
    dues_after = None
    if membership is not None:
        dues_after = ms.dues_of(membership, ms.payments_for(db, [membership.id]))
    return Receipt(
        payment=payments_read(db, [payment])[0],
        gym_name=gym.name,
        gym_phone=gym.phone,
        gym_address=gym.address,
        branch_name=branch.name if branch else None,
        member_name=member.name,
        member_code=member.member_code,
        member_phone=member.phone,
        plan_name=membership.plan_name if membership else None,
        start_date=membership.start_date if membership else None,
        end_date=membership.end_date if membership else None,
        membership_total=ms.amount_due(membership) if membership else None,
        dues_after=dues_after,
        date_display=gym.config.date_display,
    )
