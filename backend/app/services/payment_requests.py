"""Renewing from the member app (PLAN.md §5.2, §5.4).

The member pays the gym's own QR in their wallet app, then tells us the
transaction ID (and/or a screenshot). Staff with "Approve app payments" check
the gym's eSewa or bank app for the money, then approve — which sells the
membership exactly as at the desk — or reject with a reason the member sees.

Safeguards: a transaction ID is used once per gym, across payments and
pending requests; if the amount doesn't match what the membership costs,
staff must adjust the price or accept it as a part payment; every approval
records who approved it.
"""

import uuid

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.tenancy import StaffContext
from app.core.errors import AppError
from app.core.time import utcnow
from app.models.gym import Gym
from app.models.member import Member
from app.models.member_app import (
    REQUEST_APPROVED,
    REQUEST_PENDING,
    REQUEST_REJECTED,
    REQUEST_WITHDRAWN,
    PaymentRequest,
)
from app.models.membership import SOURCE_APP
from app.models.messaging import SMS_PAYMENT
from app.models.payment import GymPaymentMethod, Payment
from app.models.plan import Plan
from app.services import activity, live, reminders
from app.services import memberships as ms
from app.services.push import service as push

REF_USED = AppError(
    409, "transaction_ref_used", "That transaction ID has already been used."
)

# The wallet a gym account belongs to, as a payment method.
METHOD_FOR_ACCOUNT = {"esewa": "esewa", "khalti": "khalti", "fonepay": "fonepay"}


def ref_in_use(
    db: Session, gym_id: uuid.UUID, ref: str, exclude: uuid.UUID | None = None
) -> bool:
    if db.scalar(
        select(Payment.id).where(
            Payment.gym_id == gym_id, Payment.transaction_ref == ref
        )
    ):
        return True
    stmt = select(PaymentRequest.id).where(
        PaymentRequest.gym_id == gym_id,
        PaymentRequest.transaction_ref == ref,
        PaymentRequest.status == REQUEST_PENDING,
    )
    if exclude is not None:
        stmt = stmt.where(PaymentRequest.id != exclude)
    return bool(db.scalar(stmt))


def create(
    db: Session,
    member: Member,
    *,
    plan_id: uuid.UUID,
    payment_method_id: uuid.UUID | None,
    amount: int,
    transaction_ref: str | None,
) -> PaymentRequest:
    plan = db.get(Plan, plan_id)
    if (
        plan is None
        or plan.gym_id != member.gym_id
        or not plan.is_active
        or plan.price is None
    ):
        raise AppError(422, "bad_plan", "That plan isn't available.")
    if payment_method_id is not None:
        method = db.get(GymPaymentMethod, payment_method_id)
        if method is None or method.gym_id != member.gym_id or not method.is_active:
            raise AppError(422, "bad_method", "That payment account isn't available.")
    ref = (transaction_ref or "").strip() or None
    # Locked: a double tap on "I've paid" must not leave two requests waiting.
    ms.lock_member(db, member)
    if ref:
        ms.lock_transaction_ref(db, member.gym_id, ref)
    if ref and ref_in_use(db, member.gym_id, ref):
        raise REF_USED
    pending = db.scalar(
        select(PaymentRequest.id).where(
            PaymentRequest.member_id == member.id,
            PaymentRequest.status == REQUEST_PENDING,
        )
    )
    if pending:
        raise AppError(
            409, "request_pending", "You already have a payment waiting for the gym."
        )
    row = PaymentRequest(
        gym_id=member.gym_id,
        member_id=member.id,
        plan_id=plan.id,
        payment_method_id=payment_method_id,
        amount=amount,
        transaction_ref=ref,
        status=REQUEST_PENDING,
    )
    db.add(row)
    db.flush()
    _changed(db, row)
    return row


def _pending(row: PaymentRequest) -> None:
    if row.status != REQUEST_PENDING:
        raise AppError(
            409, "request_closed", "This request has already been dealt with."
        )


def _changed(db: Session, row: PaymentRequest) -> None:
    """The approvers' list and badge, and the member's own app."""
    live.publish(
        db, gym_id=row.gym_id, kind=live.PAYMENT_REQUEST, member_id=row.member_id
    )


def withdraw(db: Session, row: PaymentRequest) -> None:
    _pending(row)
    row.status = REQUEST_WITHDRAWN
    _changed(db, row)


def approve(
    db: Session,
    ctx: StaffContext,
    row: PaymentRequest,
    *,
    price: int | None = None,
    discount: int = 0,
    accept_part_payment: bool = False,
    request: Request | None = None,
) -> PaymentRequest:
    """`row` must be loaded FOR UPDATE: two staff approving at once would
    otherwise both see it pending and sell the membership twice."""
    _pending(row)
    member = db.get(Member, row.member_id)
    gym = db.get(Gym, ctx.gym_id)
    plan = db.get(Plan, row.plan_id)
    assert member is not None and gym is not None and plan is not None
    if row.transaction_ref:
        ms.lock_transaction_ref(db, ctx.gym_id, row.transaction_ref)
    if row.transaction_ref and ref_in_use(
        db, ctx.gym_id, row.transaction_ref, exclude=row.id
    ):
        raise REF_USED

    the_price = price if price is not None else plan.price
    if the_price is None:
        raise AppError(422, "plan_has_no_price", "Set a price for this plan.")
    admission = plan.admission_fee if ms.is_first_membership(db, member) else 0
    total = the_price - discount + admission
    if row.amount > total:
        raise AppError(
            409,
            "amount_mismatch",
            "They paid more than the membership costs. Adjust the price first.",
            expected=total,
        )
    if row.amount < total and not accept_part_payment:
        raise AppError(
            409,
            "amount_mismatch",
            "The amount doesn't match. Adjust the price, or accept a part payment.",
            expected=total,
        )

    method = (
        db.get(GymPaymentMethod, row.payment_method_id)
        if row.payment_method_id
        else None
    )
    membership, payment = ms.sell(
        db,
        ctx,
        member,
        ms.SaleIn(
            plan_id=plan.id,
            price=the_price,
            discount=discount,
            admission_fee=admission,
            source=SOURCE_APP,
            payment=ms.PaymentIn(
                amount=row.amount,
                method=METHOD_FOR_ACCOUNT.get(method.kind if method else "", "bank"),
                transaction_ref=row.transaction_ref,
                note="From the member app",
            ),
        ),
        gym.config,
        request=request,
        check_payment_permission=False,
    )
    row.status = REQUEST_APPROVED
    row.reviewed_by = ctx.staff.id
    row.reviewed_at = utcnow()
    row.membership_id = membership.id
    row.payment_id = payment.id if payment else None
    _changed(db, row)
    activity.staff_action(
        db,
        ctx.staff,
        "payment_request.approved",
        entity="payment_request",
        entity_id=row.id,
        changes={"membership_id": membership.id, "amount": row.amount},
        request=request,
    )
    reminders.after_sale(
        db, gym, member, membership, new_member=False, staff_id=ctx.staff.id
    )
    return row


def reject(
    db: Session,
    ctx: StaffContext,
    row: PaymentRequest,
    reason: str,
    *,
    request: Request | None = None,
) -> PaymentRequest:
    _pending(row)
    member = db.get(Member, row.member_id)
    gym = db.get(Gym, ctx.gym_id)
    assert member is not None and gym is not None
    row.status = REQUEST_REJECTED
    row.reject_reason = reason
    row.reviewed_by = ctx.staff.id
    row.reviewed_at = utcnow()
    _changed(db, row)
    activity.staff_action(
        db,
        ctx.staff,
        "payment_request.rejected",
        entity="payment_request",
        entity_id=row.id,
        reason=reason,
        request=request,
    )
    text = (
        f"{gym.name}: we couldn't confirm your payment: {reason}. "
        f"Please check, or ask at the desk."
    )
    push.notify(
        db,
        gym,
        member,
        title=gym.name,
        body=text,
        url=f"/{gym.slug}/renew",
        tag="payment_request",
        sms_body=f"{text} {reminders.member_link(gym)}",
        sms_kind=SMS_PAYMENT,
        created_by=ctx.staff.id,
    )
    return row
