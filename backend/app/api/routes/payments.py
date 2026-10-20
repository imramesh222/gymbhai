"""Payments the gym recorded (PLAN.md §5.2, §5.6, §7).

Payments are never deleted, only voided with a reason, and every edit is logged.
"""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api import idempotency
from app.api.deps import require
from app.api.presenters import payment_read, payments_read, staff_names
from app.api.tenancy import StaffContext, get_in_gym
from app.core.errors import AppError
from app.core.permissions import Permission
from app.core.time import NEPAL, utcnow
from app.core.whatsapp_templates import WhatsApp
from app.db.session import get_db
from app.models.gym import Gym
from app.models.member import Member
from app.models.membership import Membership
from app.models.messaging import SMS_RECEIPT, SmsMessage
from app.models.payment import KIND_PAYMENT, KIND_REFUND, Payment
from app.models.shop import ProductSale
from app.models.training import PtPackage
from app.schemas.messaging import SmsRead
from app.schemas.money import (
    PaymentCollect,
    PaymentList,
    PaymentListItem,
    PaymentRead,
    PaymentUpdate,
    Receipt,
    ReceiptLink,
    RefundCollect,
    VoidIn,
)
from app.services import activity, live, receipts, shop, tax, training
from app.services import memberships as ms
from app.services.whatsapp import service as whatsapp

router = APIRouter(prefix="/payments", tags=["payments"])

FIELDS = ("amount", "method", "transaction_ref", "paid_at", "note")


def _target(db: Session, ctx: StaffContext, payload: PaymentCollect):
    """The membership, or the personal training (§18.3), the money is for."""
    if payload.pt_package_id is not None:
        return training.load(db, ctx, payload.pt_package_id)
    assert payload.membership_id is not None
    return get_in_gym(
        db,
        Membership,
        payload.membership_id,
        ctx,
        branch_column=Membership.branch_id,
        message="No such membership.",
    )


EXCLUDED = {"membership_id", "pt_package_id"}


def _payment(
    db: Session, ctx: StaffContext, payment_id: uuid.UUID, *, for_update: bool = False
) -> Payment:
    return get_in_gym(
        db, Payment, payment_id, ctx, message="No such payment.", for_update=for_update
    )


def _member_changed(db: Session, payment: Payment) -> None:
    branch_id = None
    if payment.sale_id:
        branch_id = db.scalar(
            select(ProductSale.branch_id).where(ProductSale.id == payment.sale_id)
        )
        live.publish(db, gym_id=payment.gym_id, kind=live.SHOP, branch_id=branch_id)
        if payment.member_id is None:
            return  # a walk-in: nobody's page to tell
    if payment.membership_id:
        branch_id = db.scalar(
            select(Membership.branch_id).where(Membership.id == payment.membership_id)
        )
    elif payment.pt_package_id:
        branch_id = db.scalar(
            select(PtPackage.branch_id).where(PtPackage.id == payment.pt_package_id)
        )
        live.publish(db, gym_id=payment.gym_id, kind=live.PT, branch_id=branch_id)
    live.publish(
        db,
        gym_id=payment.gym_id,
        kind=live.MEMBER,
        member_id=payment.member_id,
        branch_id=branch_id,
    )


def _purpose(payment: Payment) -> dict[str, uuid.UUID | None]:
    if payment.sale_id:
        return {"sale_id": payment.sale_id}
    if payment.pt_package_id:
        return {"pt_package_id": payment.pt_package_id}
    return {"membership_id": payment.membership_id}


@router.post("", response_model=PaymentRead, status_code=status.HTTP_201_CREATED)
def collect(
    payload: PaymentCollect,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.PAYMENTS_COLLECT)),
) -> PaymentRead:
    """Money towards a membership or personal training: part payments of dues
    are normal (§6, §18.3)."""
    idem = idempotency.begin(db, ctx, request, payload)
    payment = ms.record_payment(
        db,
        ctx,
        _target(db, ctx, payload),
        ms.PaymentIn(**payload.model_dump(exclude=EXCLUDED)),
        request=request,
    )
    answer = payment_read(payment, {ctx.staff.id: ctx.staff.name})
    idem.finish(answer)
    db.commit()
    return answer


@router.post(
    "/refunds", response_model=PaymentRead, status_code=status.HTTP_201_CREATED
)
def refund(
    payload: RefundCollect,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.PAYMENTS_REFUND)),
) -> PaymentRead:
    idem = idempotency.begin(db, ctx, request, payload)
    payment = ms.record_payment(
        db,
        ctx,
        _target(db, ctx, payload),
        ms.PaymentIn(**payload.model_dump(exclude=EXCLUDED)),
        kind=KIND_REFUND,
        request=request,
    )
    answer = payment_read(payment, {ctx.staff.id: ctx.staff.name})
    idem.finish(answer)
    db.commit()
    return answer


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
        conditions.append(ms.payments_in_branches(ctx.branch_ids))
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
        # A walk-in's purchase at the desk has no member (§20.1).
        .outerjoin(Member, Member.id == Payment.member_id)
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
    payment = _payment(db, ctx, payment_id, for_update=True)
    if payment.voided_at is not None:
        raise AppError(409, "payment_voided", "This payment has been voided.")
    before = {name: getattr(payment, name) for name in FIELDS}
    changes = payload.model_dump(exclude_unset=True, exclude={"reason"})
    if payment.sale_id and changes.get("amount") not in (None, payment.amount):
        # What was sold says what it cost: void the sale and sell again.
        raise AppError(
            409, "sale_amount", "A sale's amount can't change: void it and sell again."
        )
    if changes.get("amount") not in (None, payment.amount):
        # An issued tax invoice is never changed (§20.4).
        tax.refuse_amount_change(db, payment)
    for name, value in changes.items():
        if value is None and name in ("amount", "method", "paid_at"):
            continue
        if name == "transaction_ref":
            value = (value or "").strip() or None
            if value:
                ms.lock_transaction_ref(db, ctx.gym_id, value)
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
        _member_changed(db, payment)
        activity.staff_action(
            db,
            ctx.staff,
            "payment.updated",
            entity="payment",
            entity_id=payment.id,
            changes={**diff, **_purpose(payment)},
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
    payment = _payment(db, ctx, payment_id, for_update=True)
    if payment.voided_at is not None:
        raise AppError(409, "payment_voided", "This payment has already been voided.")
    if payment.sale_id:
        # A sale's payment goes with the sale: its stock comes back too.
        sale = db.get(ProductSale, payment.sale_id)
        assert sale is not None
        shop.void(db, ctx, sale, payload.reason, request)
        db.commit()
        return payments_read(db, [payment])[0]
    payment.voided_at = utcnow()
    payment.voided_by = ctx.staff.id
    payment.void_reason = payload.reason
    # Its tax invoice taken back by a credit note (§20.4).
    tax.on_void(db, payment, payload.reason, ctx.staff.id)
    _member_changed(db, payment)
    activity.staff_action(
        db,
        ctx.staff,
        "payment.voided",
        entity="payment",
        entity_id=payment.id,
        changes={"amount": payment.amount, **_purpose(payment)},
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
    """A payment receipt, not a VAT invoice (§10); with a VAT-registered
    gym's tax invoice for it (§20.4)."""
    return receipts.build(db, _payment(db, ctx, payment_id))


@router.post("/{payment_id}/receipt/printed", response_model=Receipt)
def receipt_printed(
    payment_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_VIEW)),
) -> Receipt:
    """About to print the receipt: a tax invoice's print is counted, so the
    second says "Copy of original" (§20.4). The answer is what to print."""
    payment = _payment(db, ctx, payment_id)
    receipts.count_prints(db, payment)
    db.commit()
    return receipts.build(db, payment)


@router.post("/{payment_id}/receipt-link", response_model=ReceiptLink)
def receipt_link(
    payment_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_VIEW)),
) -> ReceiptLink:
    """The receipt as a PDF to download or share on WhatsApp (§16.3, 8.4)."""
    return receipts.share(receipts.build(db, _payment(db, ctx, payment_id)))


@router.post(
    "/{payment_id}/receipt-whatsapp",
    response_model=SmsRead,
    status_code=status.HTTP_201_CREATED,
)
def receipt_whatsapp(
    payment_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MESSAGES_SMS)),
) -> SmsMessage:
    """The receipt to the member on WhatsApp, the PDF behind its button
    (§19.3). It costs credits, as an SMS does; if WhatsApp can't deliver it,
    the link goes by SMS."""
    payment = _payment(db, ctx, payment_id)
    member = db.get(Member, payment.member_id) if payment.member_id else None
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    if (
        member is None
        or payment.voided_at is not None
        or not whatsapp.reachable(gym, member)
    ):
        raise AppError(
            422,
            "whatsapp_unreachable",
            "This receipt can't be sent to them on WhatsApp.",
        )
    link = receipts.share(receipts.build(db, payment))
    values = {
        "name": member.name.split()[0],
        "gym": gym.name,
        "receipt": payment.receipt_no,
        "amount": f"{payment.amount / 100:,.0f}",
    }
    message = whatsapp.queue(
        db,
        gym,
        member,
        WhatsApp("receipt", values, button=link.url.split("/receipts/", 1)[1]),
        kind=SMS_RECEIPT,
        fallback=f"{link.text}: {link.url}",
        created_by=ctx.staff.id,
    )
    activity.staff_action(
        db,
        ctx.staff,
        "receipt.sent_on_whatsapp",
        entity="payment",
        entity_id=payment.id,
        changes={"sms_id": message.id},
        request=request,
    )
    db.commit()
    return message
