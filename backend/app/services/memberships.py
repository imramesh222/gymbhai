"""Selling, renewing and editing memberships, and the money on them.

The rules that matter (PLAN.md §5, §6):

* Status is computed from dates, freezes and cancelled_at — never stored.
* Renewing early starts the day after the current membership ends, so early
  renewers lose nothing; after a lapse it starts today.
* Price, discount and admission fee are copied onto the membership at sale.
* Dues = price − discount + admission fee − payments + refunds (voided
  payments count for nothing; a cancelled membership owes nothing more).
* Every change goes to activity_log with before and after.
"""

import datetime as dt
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.tenancy import StaffContext
from app.core.calendar import plan_end_date
from app.core.errors import AppError
from app.core.gym_settings import GymSettings
from app.core.permissions import Permission
from app.core.time import today_in_nepal, utcnow
from app.models.gym import Branch
from app.models.member import Member
from app.models.membership import SOURCE_DESK, Membership, MembershipFreeze
from app.models.payment import KIND_PAYMENT, KIND_REFUND, Payment
from app.models.plan import Plan, PlanBranch
from app.services import activity, counters

ACTIVE = "active"
UPCOMING = "upcoming"
EXPIRED = "expired"
FROZEN = "frozen"
CANCELLED = "cancelled"

# Fields whose before/after the History tab shows (§5.6).
TRACKED = (
    "plan_id",
    "plan_name",
    "branch_id",
    "start_date",
    "end_date",
    "price",
    "discount",
    "admission_fee",
    "cancelled_at",
    "cancel_reason",
)


# --- computing, never storing -------------------------------------------------


def status_of(
    membership: Membership,
    freezes: Iterable[MembershipFreeze] = (),
    today: dt.date | None = None,
) -> str:
    today = today or today_in_nepal()
    if membership.cancelled_at is not None:
        return CANCELLED
    if any(f.from_date <= today <= f.to_date for f in freezes):
        return FROZEN
    if membership.start_date > today:
        return UPCOMING
    if membership.end_date < today:
        return EXPIRED
    return ACTIVE


def days_left(membership: Membership, today: dt.date | None = None) -> int:
    """Days the member can still train, today included. 0 once it has ended."""
    today = today or today_in_nepal()
    start = max(today, membership.start_date)
    return max((membership.end_date - start).days + 1, 0)


def amount_due(membership: Membership) -> int:
    if membership.cancelled_at is not None:
        return 0
    return membership.price - membership.discount + membership.admission_fee


def net_paid(payments: Iterable[Payment]) -> int:
    total = 0
    for payment in payments:
        if payment.voided_at is not None:
            continue
        total += payment.amount if payment.kind == KIND_PAYMENT else -payment.amount
    return total


def dues_of(membership: Membership, payments: Iterable[Payment]) -> int:
    if membership.cancelled_at is not None:
        return 0
    return amount_due(membership) - net_paid(payments)


def snapshot(membership: Membership) -> dict[str, Any]:
    return {field: getattr(membership, field) for field in TRACKED}


# --- loading ------------------------------------------------------------------


def payments_for(db: Session, membership_ids: Sequence[uuid.UUID]) -> list[Payment]:
    if not membership_ids:
        return []
    return list(
        db.scalars(
            select(Payment)
            .where(Payment.membership_id.in_(membership_ids))
            .order_by(Payment.paid_at)
        )
    )


def freezes_for(
    db: Session, membership_ids: Sequence[uuid.UUID]
) -> list[MembershipFreeze]:
    if not membership_ids:
        return []
    return list(
        db.scalars(
            select(MembershipFreeze)
            .where(MembershipFreeze.membership_id.in_(membership_ids))
            .order_by(MembershipFreeze.from_date)
        )
    )


def memberships_of(db: Session, member: Member) -> list[Membership]:
    return list(
        db.scalars(
            select(Membership)
            .where(
                Membership.member_id == member.id, Membership.gym_id == member.gym_id
            )
            .order_by(Membership.start_date.desc(), Membership.created_at.desc())
        )
    )


def member_dues(db: Session, member: Member) -> int:
    memberships = memberships_of(db, member)
    payments = payments_for(db, [m.id for m in memberships])
    return sum(
        dues_of(m, [p for p in payments if p.membership_id == m.id])
        for m in memberships
    )


def renewal_start(db: Session, member: Member, today: dt.date | None = None) -> dt.date:
    """The day after the current membership ends, or today after a lapse."""
    today = today or today_in_nepal()
    latest_end = db.scalar(
        select(func.max(Membership.end_date)).where(
            Membership.member_id == member.id,
            Membership.gym_id == member.gym_id,
            Membership.cancelled_at.is_(None),
        )
    )
    if latest_end is not None and latest_end >= today:
        return latest_end + dt.timedelta(days=1)
    return today


def is_first_membership(db: Session, member: Member) -> bool:
    return not db.scalar(
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.member_id == member.id,
            Membership.gym_id == member.gym_id,
            Membership.cancelled_at.is_(None),
        )
    )


def plan_covers_branch(db: Session, plan: Plan, branch_id: uuid.UUID) -> bool:
    if plan.all_branches:
        return True
    return bool(
        db.scalar(
            select(func.count())
            .select_from(PlanBranch)
            .where(PlanBranch.plan_id == plan.id, PlanBranch.branch_id == branch_id)
        )
    )


def _branch_in_gym(db: Session, ctx: StaffContext, branch_id: uuid.UUID) -> Branch:
    branch = db.get(Branch, branch_id)
    if branch is None or branch.gym_id != ctx.gym_id:
        raise AppError(422, "bad_branch", "That branch does not exist.")
    if not ctx.can_access_branch(branch.id):
        raise AppError(403, "branch_denied", "You don't work at that branch.")
    return branch


# --- payments -----------------------------------------------------------------


@dataclass
class PaymentIn:
    amount: int
    method: str
    transaction_ref: str | None = None
    paid_at: dt.datetime | None = None
    note: str | None = None


def record_payment(
    db: Session,
    ctx: StaffContext,
    membership: Membership,
    payment: PaymentIn,
    *,
    kind: str = KIND_PAYMENT,
    request: Request | None = None,
    check_permission: bool = True,
) -> Payment:
    """Record money received for (or refunded on) a membership.

    `check_permission=False` is for approving an app payment, where the
    approver's own permission (Approve app payments) has been checked.
    """
    needed = (
        Permission.PAYMENTS_COLLECT
        if kind == KIND_PAYMENT
        else Permission.PAYMENTS_REFUND
    )
    if check_permission and not ctx.can(needed):
        raise AppError(
            403,
            "permission_denied",
            "You don't have permission to do this.",
            permission=needed.value,
        )
    if payment.amount <= 0:
        raise AppError(422, "bad_amount", "The amount must be more than zero.")

    existing = payments_for(db, [membership.id])
    if kind == KIND_PAYMENT:
        if membership.cancelled_at is not None:
            raise AppError(409, "membership_cancelled", "This membership is cancelled.")
        owed = dues_of(membership, existing)
        if payment.amount > owed:
            raise AppError(
                422,
                "overpayment",
                "That is more than is owed on this membership.",
                owed=owed,
            )
    elif payment.amount > net_paid(existing):
        raise AppError(422, "refund_too_large", "You can't refund more than was paid.")

    ref = (payment.transaction_ref or "").strip() or None
    if ref and db.scalar(
        select(Payment.id).where(
            Payment.gym_id == ctx.gym_id, Payment.transaction_ref == ref
        )
    ):
        raise AppError(
            409, "transaction_ref_used", "That transaction ID has already been used."
        )

    row = Payment(
        gym_id=ctx.gym_id,
        member_id=membership.member_id,
        membership_id=membership.id,
        kind=kind,
        amount=payment.amount,
        method=payment.method,
        transaction_ref=ref,
        paid_at=payment.paid_at or utcnow(),
        receipt_no=counters.next_value(db, ctx.gym_id, counters.RECEIPT_NO),
        received_by=ctx.staff.id,
        note=payment.note,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            409, "transaction_ref_used", "That transaction ID has already been used."
        ) from exc

    activity.staff_action(
        db,
        ctx.staff,
        "payment.recorded" if kind == KIND_PAYMENT else "refund.recorded",
        entity="payment",
        entity_id=row.id,
        changes={
            "membership_id": membership.id,
            "member_id": membership.member_id,
            "amount": row.amount,
            "method": row.method,
            "transaction_ref": row.transaction_ref,
            "receipt_no": row.receipt_no,
        },
        request=request,
    )
    return row


# --- selling ------------------------------------------------------------------


@dataclass
class SaleIn:
    plan_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    price: int | None = None
    discount: int = 0
    # None means "the plan's fee on a first membership, nothing on a renewal".
    admission_fee: int | None = None
    payment: PaymentIn | None = None
    source: str = SOURCE_DESK


def sell(
    db: Session,
    ctx: StaffContext,
    member: Member,
    sale: SaleIn,
    config: GymSettings,
    *,
    request: Request | None = None,
    check_payment_permission: bool = True,
) -> tuple[Membership, Payment | None]:
    """A new membership or a renewal, with an optional payment taken now."""
    plan = db.get(Plan, sale.plan_id)
    if plan is None or plan.gym_id != ctx.gym_id:
        raise AppError(422, "bad_plan", "That plan does not exist.")
    if not plan.is_active:
        raise AppError(422, "plan_hidden", "That plan is no longer offered.")

    branch = _branch_in_gym(db, ctx, sale.branch_id or member.home_branch_id)
    if not plan_covers_branch(db, plan, branch.id):
        raise AppError(
            422, "plan_not_at_branch", "That plan isn't sold at this branch."
        )

    price = sale.price if sale.price is not None else plan.price
    if price is None:
        raise AppError(
            422, "plan_has_no_price", "Set a price for this plan, or enter one here."
        )
    first = is_first_membership(db, member)
    admission = (
        sale.admission_fee
        if sale.admission_fee is not None
        else (plan.admission_fee if first else 0)
    )
    if sale.discount < 0 or sale.discount > price + admission:
        raise AppError(
            422, "bad_discount", "The discount can't be more than the total."
        )

    start = sale.start_date or renewal_start(db, member)
    end = sale.end_date or plan_end_date(
        start,
        months=plan.duration_months,
        days=plan.duration_days,
        calendar=config.plan_months,
    )
    if end < start:
        raise AppError(422, "bad_dates", "The end date is before the start date.")

    membership = Membership(
        gym_id=ctx.gym_id,
        member_id=member.id,
        plan_id=plan.id,
        plan_name=plan.name,
        branch_id=branch.id,
        start_date=start,
        end_date=end,
        price=price,
        discount=sale.discount,
        admission_fee=admission,
        created_by=ctx.staff.id,
        source=sale.source,
    )
    db.add(membership)
    db.flush()
    activity.staff_action(
        db,
        ctx.staff,
        "membership.created",
        entity="membership",
        entity_id=membership.id,
        changes={"member_id": member.id, "renewal": not first, **snapshot(membership)},
        request=request,
    )

    payment = None
    if sale.payment is not None and sale.payment.amount > 0:
        payment = record_payment(
            db,
            ctx,
            membership,
            sale.payment,
            request=request,
            check_permission=check_payment_permission,
        )
    return membership, payment


# --- editing ------------------------------------------------------------------


def _log_edit(
    db: Session,
    ctx: StaffContext,
    membership: Membership,
    action: str,
    before: dict[str, Any],
    *,
    reason: str | None = None,
    extra: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    changes = activity.diff(before, snapshot(membership))
    if extra:
        changes.update(extra)
    activity.staff_action(
        db,
        ctx.staff,
        action,
        entity="membership",
        entity_id=membership.id,
        changes=changes,
        reason=reason,
        request=request,
    )


def edit(
    db: Session,
    ctx: StaffContext,
    membership: Membership,
    changes: dict[str, Any],
    config: GymSettings,
    *,
    reason: str | None = None,
    request: Request | None = None,
) -> Membership:
    """Change dates, price, discount, admission fee, plan or branch (§5.6).

    Changing the plan recalculates the end date and the price from the new plan
    unless those are given too; the difference shows up as dues to collect.
    """
    if membership.cancelled_at is not None:
        raise AppError(409, "membership_cancelled", "This membership is cancelled.")
    before = snapshot(membership)

    new_plan_id = changes.get("plan_id")
    if new_plan_id is not None and new_plan_id != membership.plan_id:
        plan = db.get(Plan, new_plan_id)
        if plan is None or plan.gym_id != ctx.gym_id:
            raise AppError(422, "bad_plan", "That plan does not exist.")
        membership.plan_id = plan.id
        membership.plan_name = plan.name
        if "end_date" not in changes:
            changes["end_date"] = plan_end_date(
                changes.get("start_date", membership.start_date),
                months=plan.duration_months,
                days=plan.duration_days,
                calendar=config.plan_months,
            )
        if "price" not in changes:
            if plan.price is None:
                raise AppError(
                    422, "plan_has_no_price", "Set a price for this plan, or enter one."
                )
            changes["price"] = plan.price

    if changes.get("branch_id") is not None:
        _branch_in_gym(db, ctx, changes["branch_id"])

    for field in (
        "start_date",
        "end_date",
        "price",
        "discount",
        "admission_fee",
        "branch_id",
    ):
        if changes.get(field) is not None:
            setattr(membership, field, changes[field])

    if membership.end_date < membership.start_date:
        raise AppError(422, "bad_dates", "The end date is before the start date.")
    if membership.discount > membership.price + membership.admission_fee:
        raise AppError(
            422, "bad_discount", "The discount can't be more than the total."
        )

    _log_edit(
        db,
        ctx,
        membership,
        "membership.updated",
        before,
        reason=reason,
        request=request,
    )
    return membership


def extend(
    db: Session,
    ctx: StaffContext,
    membership: Membership,
    days: int,
    reason: str,
    *,
    request: Request | None = None,
) -> Membership:
    if membership.cancelled_at is not None:
        raise AppError(409, "membership_cancelled", "This membership is cancelled.")
    before = snapshot(membership)
    membership.end_date += dt.timedelta(days=days)
    _log_edit(
        db,
        ctx,
        membership,
        "membership.extended",
        before,
        reason=reason,
        extra={"days": days},
        request=request,
    )
    return membership


def extend_all(
    db: Session,
    ctx: StaffContext,
    days: int,
    reason: str,
    *,
    branch_id: uuid.UUID | None = None,
    request: Request | None = None,
) -> int:
    """Every current and upcoming membership, e.g. the gym shut for Dashain."""
    today = today_in_nepal()
    stmt = select(Membership).where(
        Membership.gym_id == ctx.gym_id,
        Membership.cancelled_at.is_(None),
        Membership.end_date >= today,
    )
    if branch_id is not None:
        _branch_in_gym(db, ctx, branch_id)
        stmt = stmt.where(Membership.branch_id == branch_id)
    elif ctx.branch_ids is not None:
        stmt = stmt.where(Membership.branch_id.in_(ctx.branch_ids))

    batch = uuid.uuid4()
    count = 0
    for membership in db.scalars(stmt.with_for_update()):
        before = snapshot(membership)
        membership.end_date += dt.timedelta(days=days)
        _log_edit(
            db,
            ctx,
            membership,
            "membership.extended",
            before,
            reason=reason,
            extra={"days": days, "batch": batch},
            request=request,
        )
        count += 1

    activity.staff_action(
        db,
        ctx.staff,
        "membership.extended_all",
        entity="gym",
        entity_id=ctx.gym_id,
        changes={"days": days, "branch_id": branch_id, "count": count, "batch": batch},
        reason=reason,
        request=request,
    )
    return count


def freeze(
    db: Session,
    ctx: StaffContext,
    membership: Membership,
    from_date: dt.date,
    to_date: dt.date,
    reason: str | None,
    *,
    request: Request | None = None,
) -> MembershipFreeze:
    """Pause a membership; the end date moves by the frozen days (§5.6)."""
    if membership.cancelled_at is not None:
        raise AppError(409, "membership_cancelled", "This membership is cancelled.")
    if to_date < from_date:
        raise AppError(422, "bad_dates", "The freeze ends before it starts.")
    if from_date > membership.end_date or to_date < membership.start_date:
        raise AppError(422, "bad_dates", "The freeze must fall within the membership.")
    for existing in freezes_for(db, [membership.id]):
        if existing.from_date <= to_date and from_date <= existing.to_date:
            raise AppError(
                409, "freeze_overlaps", "It is already frozen on some of those days."
            )

    before = snapshot(membership)
    row = MembershipFreeze(
        gym_id=ctx.gym_id,
        membership_id=membership.id,
        from_date=from_date,
        to_date=to_date,
        reason=reason,
    )
    db.add(row)
    frozen_days = (to_date - from_date).days + 1
    membership.end_date += dt.timedelta(days=frozen_days)
    db.flush()
    _log_edit(
        db,
        ctx,
        membership,
        "membership.frozen",
        before,
        reason=reason,
        extra={
            "freeze_id": row.id,
            "from": from_date,
            "to": to_date,
            "days": frozen_days,
        },
        request=request,
    )
    return row


def unfreeze(
    db: Session,
    ctx: StaffContext,
    membership: Membership,
    row: MembershipFreeze,
    *,
    request: Request | None = None,
) -> Membership:
    """End a freeze today (or remove a future one), giving back unused days."""
    today = today_in_nepal()
    if row.to_date < today:
        raise AppError(409, "freeze_over", "That freeze has already ended.")
    before = snapshot(membership)
    old_days = (row.to_date - row.from_date).days + 1
    if row.from_date >= today:
        # Not started yet: remove it entirely.
        membership.end_date -= dt.timedelta(days=old_days)
        db.delete(row)
        new_days = 0
    else:
        row.to_date = today - dt.timedelta(days=1)
        new_days = (row.to_date - row.from_date).days + 1
        membership.end_date -= dt.timedelta(days=old_days - new_days)
    _log_edit(
        db,
        ctx,
        membership,
        "membership.unfrozen",
        before,
        extra={"freeze_id": row.id, "days_before": old_days, "days_after": new_days},
        request=request,
    )
    return membership


def cancel(
    db: Session,
    ctx: StaffContext,
    membership: Membership,
    reason: str,
    refund: PaymentIn | None,
    *,
    request: Request | None = None,
) -> Payment | None:
    if membership.cancelled_at is not None:
        raise AppError(
            409, "membership_cancelled", "This membership is already cancelled."
        )
    refund_row = None
    if refund is not None and refund.amount > 0:
        refund_row = record_payment(
            db, ctx, membership, refund, kind=KIND_REFUND, request=request
        )
    before = snapshot(membership)
    membership.cancelled_at = utcnow()
    membership.cancel_reason = reason
    _log_edit(
        db,
        ctx,
        membership,
        "membership.cancelled",
        before,
        reason=reason,
        request=request,
    )
    return refund_row


def delete(
    db: Session,
    ctx: StaffContext,
    membership: Membership,
    *,
    request: Request | None = None,
) -> None:
    """Only a mistake nobody has used: no check-ins, no payments standing (§5.6)."""
    payments = payments_for(db, [membership.id])
    if any(p.voided_at is None for p in payments):
        raise AppError(
            409,
            "membership_has_payments",
            "Void its payments first, or cancel the membership instead.",
        )
    if has_check_ins(db, membership):
        raise AppError(
            409,
            "membership_has_check_ins",
            "Someone has trained on this membership. Cancel it instead.",
        )
    activity.staff_action(
        db,
        ctx.staff,
        "membership.deleted",
        entity="membership",
        entity_id=membership.id,
        changes={"member_id": membership.member_id, **snapshot(membership)},
        request=request,
    )
    db.delete(membership)


def has_check_ins(db: Session, membership: Membership) -> bool:
    from app.models.member_app import LET_IN, CheckIn

    return bool(
        db.scalar(
            select(CheckIn.id).where(
                CheckIn.membership_id == membership.id, CheckIn.result.in_(LET_IN)
            )
        )
    )
