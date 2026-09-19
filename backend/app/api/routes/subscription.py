"""The gym's subscription with us (PLAN.md §5.7): see it, and pay for it.

No gateway: the owner pays our eSewa or bank account and sends the
transaction ID; we check it and activate from /admin. Allowed even after the
subscription has lapsed — paying is how a gym gets out of read-only.
"""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.tenancy import StaffContext, for_gym
from app.core.config import settings
from app.core.errors import AppError
from app.core.permissions import Permission
from app.db.session import get_db
from app.models.billing import PlatformPlan
from app.models.platform import SubscriptionPayment
from app.schemas.platform import (
    PlatformPlanRead,
    SubscriptionOverview,
    SubscriptionPaymentIn,
    SubscriptionPaymentRead,
)
from app.services import activity, subscription
from app.services.sms import service as sms

router = APIRouter(prefix="/subscription", tags=["subscription"])

SEE = require(Permission.SETUP_GYM)
PAY = require(Permission.SETUP_GYM, allow_when_lapsed=True)


def payment_read(db: Session, row: SubscriptionPayment) -> SubscriptionPaymentRead:
    read = SubscriptionPaymentRead.model_validate(row)
    if row.platform_plan_id:
        plan = db.get(PlatformPlan, row.platform_plan_id)
        read.plan_name = plan.name if plan else None
    return read


@router.get("", response_model=SubscriptionOverview)
def overview(
    db: Session = Depends(get_db), ctx: StaffContext = Depends(SEE)
) -> SubscriptionOverview:
    state = subscription.state(db, ctx.gym_id)
    plans = db.scalars(
        select(PlatformPlan)
        .where(PlatformPlan.is_active)
        .order_by(PlatformPlan.monthly_price.nulls_last())
    )
    payments = db.scalars(
        for_gym(select(SubscriptionPayment), SubscriptionPayment, ctx)
        .order_by(SubscriptionPayment.created_at.desc())
        .limit(20)
    )
    return SubscriptionOverview(
        status=state.status,
        plan_name=state.plan_name,
        starts_on=state.starts_on,
        ends_on=state.ends_on,
        days_left=state.days_left,
        phase=state.phase,
        grace_ends_on=state.grace_ends_on,
        active_members=state.active_members,
        max_active_members=state.max_active_members,
        over_limit=state.over_limit,
        sms_balance=sms.balance(db, ctx.gym_id),
        plans=[PlatformPlanRead.model_validate(p) for p in plans],
        payments=[payment_read(db, p) for p in payments],
        pay_to={
            "name": settings.platform_pay_to_name,
            "esewa": settings.platform_pay_to_esewa,
            "bank": settings.platform_pay_to_bank,
        },
    )


@router.post(
    "/payments",
    response_model=SubscriptionPaymentRead,
    status_code=status.HTTP_201_CREATED,
)
def send_payment(
    payload: SubscriptionPaymentIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(PAY),
) -> SubscriptionPaymentRead:
    """ "We've paid you": a transaction ID for us to check (§5.7)."""
    if payload.platform_plan_id is not None:
        plan = db.get(PlatformPlan, payload.platform_plan_id)
        if plan is None or not plan.is_active:
            raise AppError(422, "bad_plan", "That plan isn't available.")
    ref = payload.transaction_ref.strip()
    if db.scalar(
        select(SubscriptionPayment.id).where(
            SubscriptionPayment.transaction_ref == ref,
            SubscriptionPayment.status != "rejected",
        )
    ):
        raise AppError(
            409, "transaction_ref_used", "That transaction ID has already been sent."
        )
    row = SubscriptionPayment(
        gym_id=ctx.gym_id,
        kind=payload.kind,
        platform_plan_id=payload.platform_plan_id
        if payload.kind == "subscription"
        else None,
        months=payload.months if payload.kind == "subscription" else None,
        sms_credits=payload.sms_credits if payload.kind == "sms" else None,
        amount=payload.amount,
        transaction_ref=ref,
        status="pending",
        submitted_by=ctx.staff.id,
    )
    db.add(row)
    db.flush()
    activity.staff_action(
        db,
        ctx.staff,
        "subscription.payment_sent",
        entity="subscription_payment",
        entity_id=row.id,
        changes=payload.model_dump(),
        request=request,
    )
    db.commit()
    return payment_read(db, row)
