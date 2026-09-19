"""Platform admin: us (PLAN.md §2, §7 /admin, §8 "Platform admin").

Every gym, their subscriptions and SMS credits. Prices live in
platform_plans and are edited here — never written into the code.
Every action is in the activity log under the gym it touched.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_platform_admin
from app.core.errors import AppError, not_found
from app.core.security import hash_password
from app.core.time import utcnow
from app.db.session import get_db
from app.models.activity import ACTOR_STAFF
from app.models.billing import PlatformPlan
from app.models.gym import GYM_ACTIVE, GYM_SUSPENDED, Gym
from app.models.messaging import SMS_PLATFORM
from app.models.platform import KIND_SMS, KIND_SUBSCRIPTION, SubscriptionPayment
from app.models.staff import StaffUser
from app.schemas.platform import (
    AdminGym,
    ApproveSubscriptionIn,
    CreditsIn,
    GrantIn,
    OwnerPasswordIn,
    PlatformPlanIn,
    PlatformPlanRead,
    PlatformPlanUpdate,
    ReasonIn,
    SubscriptionPaymentRead,
)
from app.services import activity, sessions, subscription
from app.services.sms import service as sms

router = APIRouter(prefix="/admin", tags=["platform admin"])

ADMIN = Depends(require_platform_admin)


def _gym(db: Session, gym_id: uuid.UUID) -> Gym:
    gym = db.get(Gym, gym_id)
    if gym is None:
        raise not_found("No such gym.")
    return gym


def _owner(db: Session, gym_id: uuid.UUID) -> StaffUser | None:
    return db.scalars(
        select(StaffUser).where(StaffUser.gym_id == gym_id, StaffUser.is_owner)
    ).first()


def _log(db, admin: StaffUser, gym_id, action: str, request: Request, **kwargs) -> None:
    activity.record(
        db,
        gym_id=gym_id,
        actor_type=ACTOR_STAFF,
        actor_id=admin.id,
        action=action,
        request=request,
        **kwargs,
    )


def _tell_owner(db: Session, gym: Gym, text: str) -> None:
    owner = _owner(db, gym.id)
    if owner is not None and owner.phone:
        sms.queue(db, gym_id=gym.id, to=owner.phone, body=text, kind=SMS_PLATFORM)


def _payment_read(db: Session, row: SubscriptionPayment) -> SubscriptionPaymentRead:
    read = SubscriptionPaymentRead.model_validate(row)
    gym = db.get(Gym, row.gym_id)
    read.gym_name = gym.name if gym else None
    if row.platform_plan_id:
        plan = db.get(PlatformPlan, row.platform_plan_id)
        read.plan_name = plan.name if plan else None
    return read


# --- gyms ---------------------------------------------------------------------------


def _admin_gym(db: Session, gym: Gym) -> AdminGym:
    owner = _owner(db, gym.id)
    state = subscription.state(db, gym.id)
    pending = db.scalar(
        select(func.count())
        .select_from(SubscriptionPayment)
        .where(
            SubscriptionPayment.gym_id == gym.id,
            SubscriptionPayment.status == "pending",
        )
    )
    return AdminGym(
        id=gym.id,
        slug=gym.slug,
        name=gym.name,
        status=gym.status,
        owner_name=owner.name if owner else None,
        owner_phone=owner.phone if owner else None,
        owner_email=owner.email if owner else None,
        created_at=gym.created_at,
        subscription_status=state.status,
        plan_name=state.plan_name,
        ends_on=state.ends_on,
        phase=state.phase,
        active_members=state.active_members,
        sms_balance=sms.balance(db, gym.id),
        pending_payments=pending or 0,
    )


@router.get("/gyms", response_model=list[AdminGym])
def list_gyms(
    q: Annotated[str | None, Query(max_length=80)] = None,
    db: Session = Depends(get_db),
    admin: StaffUser = ADMIN,
) -> list[AdminGym]:
    stmt = select(Gym).order_by(Gym.created_at.desc())
    if q:
        stmt = stmt.where(Gym.name.ilike(f"%{q}%") | Gym.slug.ilike(f"%{q}%"))
    return [_admin_gym(db, g) for g in db.scalars(stmt.limit(500))]


@router.get("/gyms/{gym_id}", response_model=AdminGym)
def get_gym(
    gym_id: uuid.UUID, db: Session = Depends(get_db), admin: StaffUser = ADMIN
) -> AdminGym:
    return _admin_gym(db, _gym(db, gym_id))


@router.post("/gyms/{gym_id}/subscription", response_model=AdminGym)
def grant(
    gym_id: uuid.UUID,
    payload: GrantIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: StaffUser = ADMIN,
) -> AdminGym:
    """Activate or extend, e.g. after a payment made outside the app."""
    gym = _gym(db, gym_id)
    if (
        payload.platform_plan_id
        and db.get(PlatformPlan, payload.platform_plan_id) is None
    ):
        raise AppError(422, "bad_plan", "No such plan.")
    row = subscription.extend(
        db,
        gym.id,
        platform_plan_id=payload.platform_plan_id,
        months=payload.months,
        ends_on=payload.ends_on,
    )
    _log(
        db,
        admin,
        gym.id,
        "subscription.granted",
        request,
        entity="gym",
        entity_id=gym.id,
        changes={"ends_on": row.ends_on, "platform_plan_id": row.platform_plan_id},
    )
    _tell_owner(
        db,
        gym,
        f"GymBhai: your subscription is active until {row.ends_on:%d %b %Y}. "
        "Thank you!",
    )
    db.commit()
    return _admin_gym(db, gym)


@router.post("/gyms/{gym_id}/sms-credits", response_model=AdminGym)
def add_credits(
    gym_id: uuid.UUID,
    payload: CreditsIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: StaffUser = ADMIN,
) -> AdminGym:
    gym = _gym(db, gym_id)
    sms.add_credits(db, gym.id, payload.credits, f"admin: {payload.reason}")
    _log(
        db,
        admin,
        gym.id,
        "sms.credits_added",
        request,
        entity="gym",
        entity_id=gym.id,
        changes={"credits": payload.credits},
        reason=payload.reason,
    )
    db.commit()
    return _admin_gym(db, gym)


@router.post("/gyms/{gym_id}/suspend", response_model=AdminGym)
def suspend(
    gym_id: uuid.UUID,
    payload: ReasonIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: StaffUser = ADMIN,
) -> AdminGym:
    """Staff can't sign in, and the member app and door stop. For abuse, not
    for an unpaid bill: that only makes the dashboard read-only (§5.7)."""
    gym = _gym(db, gym_id)
    gym.status = GYM_SUSPENDED
    _log(
        db,
        admin,
        gym.id,
        "gym.suspended",
        request,
        entity="gym",
        entity_id=gym.id,
        reason=payload.reason,
    )
    db.commit()
    return _admin_gym(db, gym)


@router.post("/gyms/{gym_id}/unsuspend", response_model=AdminGym)
def unsuspend(
    gym_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    admin: StaffUser = ADMIN,
) -> AdminGym:
    gym = _gym(db, gym_id)
    gym.status = GYM_ACTIVE
    _log(db, admin, gym.id, "gym.unsuspended", request, entity="gym", entity_id=gym.id)
    db.commit()
    return _admin_gym(db, gym)


@router.post("/gyms/{gym_id}/owner-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_owner_password(
    gym_id: uuid.UUID,
    payload: OwnerPasswordIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: StaffUser = ADMIN,
) -> None:
    """For an owner locked out of their own gym. Signs them out everywhere."""
    gym = _gym(db, gym_id)
    owner = _owner(db, gym.id)
    if owner is None:
        raise not_found("This gym has no owner account.")
    owner.password_hash = hash_password(payload.new_password)
    sessions.revoke_all(db, owner)
    _log(
        db,
        admin,
        gym.id,
        "owner.password_reset",
        request,
        entity="staff",
        entity_id=owner.id,
    )
    db.commit()


# --- payments sent to us -----------------------------------------------------------


@router.get("/subscription-payments", response_model=list[SubscriptionPaymentRead])
def list_payments(
    payment_status: Annotated[
        str, Query(alias="status", pattern="^(pending|approved|rejected)$")
    ] = "pending",
    db: Session = Depends(get_db),
    admin: StaffUser = ADMIN,
) -> list[SubscriptionPaymentRead]:
    rows = db.scalars(
        select(SubscriptionPayment)
        .where(SubscriptionPayment.status == payment_status)
        .order_by(SubscriptionPayment.created_at)
        .limit(500)
    )
    return [_payment_read(db, r) for r in rows]


def _pending(db: Session, payment_id: uuid.UUID) -> SubscriptionPayment:
    row = db.get(SubscriptionPayment, payment_id)
    if row is None:
        raise not_found("No such payment.")
    if row.status != "pending":
        raise AppError(
            409, "request_closed", "This payment has already been dealt with."
        )
    return row


@router.post(
    "/subscription-payments/{payment_id}/approve",
    response_model=SubscriptionPaymentRead,
)
def approve_payment(
    payment_id: uuid.UUID,
    payload: ApproveSubscriptionIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: StaffUser = ADMIN,
) -> SubscriptionPaymentRead:
    row = _pending(db, payment_id)
    gym = _gym(db, row.gym_id)
    if row.kind == KIND_SUBSCRIPTION:
        months = payload.months or row.months
        plan_id = payload.platform_plan_id or row.platform_plan_id
        period = subscription.extend(
            db, gym.id, platform_plan_id=plan_id, months=months
        )
        plan = db.get(PlatformPlan, plan_id) if plan_id else None
        if plan is not None and plan.included_sms and months:
            sms.add_credits(
                db, gym.id, plan.included_sms * months, f"plan: {plan.name}"
            )
        message = (
            f"GymBhai: payment received. Your subscription is active until "
            f"{period.ends_on:%d %b %Y}. Thank you!"
        )
    elif row.kind == KIND_SMS:
        credits = payload.sms_credits or row.sms_credits or 0
        sms.add_credits(db, gym.id, credits, "top-up")
        message = f"GymBhai: payment received. {credits} SMS credits added. Thank you!"
    else:
        raise AppError(422, "bad_kind", "Unknown payment kind.")
    row.status = "approved"
    row.reviewed_by = admin.id
    row.reviewed_at = utcnow()
    _log(
        db,
        admin,
        gym.id,
        "subscription.payment_approved",
        request,
        entity="subscription_payment",
        entity_id=row.id,
    )
    _tell_owner(db, gym, message)
    db.commit()
    return _payment_read(db, row)


@router.post(
    "/subscription-payments/{payment_id}/reject", response_model=SubscriptionPaymentRead
)
def reject_payment(
    payment_id: uuid.UUID,
    payload: ReasonIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: StaffUser = ADMIN,
) -> SubscriptionPaymentRead:
    row = _pending(db, payment_id)
    gym = _gym(db, row.gym_id)
    row.status = "rejected"
    row.reject_reason = payload.reason
    row.reviewed_by = admin.id
    row.reviewed_at = utcnow()
    _log(
        db,
        admin,
        gym.id,
        "subscription.payment_rejected",
        request,
        entity="subscription_payment",
        entity_id=row.id,
        reason=payload.reason,
    )
    _tell_owner(db, gym, f"GymBhai: we couldn't confirm your payment: {payload.reason}")
    db.commit()
    return _payment_read(db, row)


# --- our price list ----------------------------------------------------------------


@router.get("/plans", response_model=list[PlatformPlanRead])
def list_plans(
    db: Session = Depends(get_db), admin: StaffUser = ADMIN
) -> list[PlatformPlan]:
    return list(db.scalars(select(PlatformPlan).order_by(PlatformPlan.created_at)))


@router.post(
    "/plans", response_model=PlatformPlanRead, status_code=status.HTTP_201_CREATED
)
def create_plan(
    payload: PlatformPlanIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: StaffUser = ADMIN,
) -> PlatformPlan:
    plan = PlatformPlan(**payload.model_dump())
    db.add(plan)
    db.flush()
    _log(
        db,
        admin,
        None,
        "platform_plan.created",
        request,
        entity="platform_plan",
        entity_id=plan.id,
        changes=payload.model_dump(),
    )
    db.commit()
    return plan


@router.patch("/plans/{plan_id}", response_model=PlatformPlanRead)
def update_plan(
    plan_id: uuid.UUID,
    payload: PlatformPlanUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: StaffUser = ADMIN,
) -> PlatformPlan:
    plan = db.get(PlatformPlan, plan_id)
    if plan is None:
        raise not_found("No such plan.")
    fields = PlatformPlanIn.model_fields
    before = {f: getattr(plan, f) for f in fields}
    for name, value in payload.model_dump(exclude_unset=True).items():
        if value is None and name in ("name", "included_sms", "is_active"):
            continue
        setattr(plan, name, value)
    diff = activity.diff(before, {f: getattr(plan, f) for f in fields})
    if diff:
        _log(
            db,
            admin,
            None,
            "platform_plan.updated",
            request,
            entity="platform_plan",
            entity_id=plan.id,
            changes=diff,
        )
    db.commit()
    return plan
