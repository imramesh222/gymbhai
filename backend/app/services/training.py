"""Personal training: selling it, the sessions, the money (PLAN.md §18.3).

The rules that matter:

* Status is computed, never stored: upcoming, active, used up (a pack with
  every session recorded), ended, cancelled.
* Dues = price − discount − payments + refunds; a cancelled package owes
  nothing more. Payments are ordinary payments, recorded by
  memberships.record_payment, and never count towards a membership's dues.
* A session falls within the package's dates, never on a cancelled package,
  and never beyond what a pack holds. A mistake is voided with a reason.
* Its trainer records a package's sessions; Sell personal training records
  or voids anyone's.
* Every change goes to activity_log with before and after.
"""

import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.api.tenancy import StaffContext
from app.core.calendar import plan_end_date
from app.core.errors import AppError, not_found
from app.core.gym_settings import GymSettings
from app.core.permissions import Permission
from app.core.time import today_in_nepal, utcnow
from app.models.member import Member
from app.models.payment import KIND_REFUND, Payment
from app.models.staff import StaffUser
from app.models.training import KIND_SESSIONS, PtPackage, PtPlan, PtSession
from app.services import activity, live
from app.services import memberships as ms

ACTIVE = "active"
UPCOMING = "upcoming"
USED_UP = "used_up"
ENDED = "ended"
CANCELLED = "cancelled"
# Still to train: on the trainer's list, and on the member's app.
CURRENT = (ACTIVE, UPCOMING)

# Fields whose before/after the History tab shows (§5.6).
TRACKED = (
    "plan_name",
    "trainer_id",
    "branch_id",
    "start_date",
    "end_date",
    "price",
    "discount",
    "cancelled_at",
    "cancel_reason",
)


# --- computing, never storing -------------------------------------------------


def status_of(package: PtPackage, used: int, today: dt.date | None = None) -> str:
    today = today or today_in_nepal()
    if package.cancelled_at is not None:
        return CANCELLED
    if package.start_date > today:
        return UPCOMING
    if package.sessions is not None and used >= package.sessions:
        return USED_UP
    if package.end_date < today:
        return ENDED
    return ACTIVE


def sessions_left(package: PtPackage, used: int) -> int | None:
    """None for monthly training, which doesn't count sessions."""
    if package.sessions is None:
        return None
    return max(package.sessions - used, 0)


def days_left(package: PtPackage, today: dt.date | None = None) -> int:
    """Days they can still train, today included. 0 once it has ended."""
    today = today or today_in_nepal()
    start = max(today, package.start_date)
    return max((package.end_date - start).days + 1, 0)


def total_of(package: PtPackage) -> int:
    return package.price - package.discount


def dues_of(package: PtPackage, payments: Iterable[Payment]) -> int:
    return ms.owed(package, payments)


def snapshot(package: PtPackage) -> dict[str, Any]:
    return {field: getattr(package, field) for field in TRACKED}


@dataclass
class Tally:
    """A package's sessions and money, from rows loaded for many at once."""

    used: int = 0
    last_on: dt.date | None = None
    paid: int = 0
    dues: int = 0


def tallies(
    db: Session,
    packages: Sequence[PtPackage],
    payments: dict[uuid.UUID, list[Payment]] | None = None,
) -> dict[uuid.UUID, Tally]:
    """Sessions used, the last one, and money, for each package: two queries
    however many packages, one if their payments are already loaded."""
    ids = [p.id for p in packages]
    found: dict[uuid.UUID, Tally] = {i: Tally() for i in ids}
    if not ids:
        return found
    for package_id, used, last_on in db.execute(
        select(PtSession.package_id, func.count(), func.max(PtSession.trained_on))
        .where(PtSession.package_id.in_(ids), PtSession.voided_at.is_(None))
        .group_by(PtSession.package_id)
    ):
        found[package_id].used = used
        found[package_id].last_on = last_on
    paid = payments if payments is not None else payments_by_package(db, ids)
    for package in packages:
        found[package.id].paid = ms.net_paid(paid[package.id])
        found[package.id].dues = dues_of(package, paid[package.id])
    return found


def payments_by_package(
    db: Session, package_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[Payment]]:
    found: dict[uuid.UUID, list[Payment]] = defaultdict(list)
    if package_ids:
        for payment in db.scalars(
            select(Payment)
            .where(Payment.pt_package_id.in_(package_ids))
            .order_by(Payment.paid_at)
        ):
            found[payment.pt_package_id].append(payment)  # type: ignore[index]
    return found


def session_log(
    db: Session, package_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[PtSession]]:
    """Every session, voided ones too, newest first."""
    found: dict[uuid.UUID, list[PtSession]] = defaultdict(list)
    if package_ids:
        for row in db.scalars(
            select(PtSession)
            .where(PtSession.package_id.in_(package_ids))
            .order_by(PtSession.trained_on.desc(), PtSession.created_at.desc())
        ):
            found[row.package_id].append(row)
    return found


# --- trainers -----------------------------------------------------------------


def trainers(db: Session, gym_id: uuid.UUID) -> list[StaffUser]:
    """Who may be given clients: staff who train members, and the owner."""
    return list(
        db.scalars(
            select(StaffUser)
            .where(
                StaffUser.gym_id == gym_id,
                StaffUser.is_active,
                or_(
                    StaffUser.is_owner,
                    StaffUser.permissions.contains([Permission.PT_TRAIN.value]),
                ),
            )
            .order_by(StaffUser.is_owner.desc(), StaffUser.name)
        )
    )


def _trainer(db: Session, ctx: StaffContext, trainer_id: uuid.UUID) -> StaffUser:
    trainer = next((s for s in trainers(db, ctx.gym_id) if s.id == trainer_id), None)
    if trainer is None:
        raise AppError(
            422,
            "bad_trainer",
            "Choose one of the gym's trainers: staff who may train members.",
        )
    return trainer


# --- loading ------------------------------------------------------------------


def visible(ctx: StaffContext) -> Select:
    """The gym's packages, at the branches the caller works at."""
    stmt = select(PtPackage).where(PtPackage.gym_id == ctx.gym_id)
    if ctx.branch_ids is not None:
        stmt = stmt.where(PtPackage.branch_id.in_(ctx.branch_ids))
    return stmt


def load(
    db: Session, ctx: StaffContext, package_id: uuid.UUID, *, for_update: bool = False
) -> PtPackage:
    """One of this gym's packages, at a branch the caller works at, or 404."""
    stmt = visible(ctx).where(PtPackage.id == package_id)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    package = db.scalar(stmt)
    if package is None:
        raise not_found("No such personal training.")
    return package


def load_session(
    db: Session, ctx: StaffContext, session_id: uuid.UUID
) -> tuple[PtSession, PtPackage]:
    """A session and its package, both locked, or 404."""
    row = db.scalar(
        select(PtSession).where(
            PtSession.id == session_id, PtSession.gym_id == ctx.gym_id
        )
    )
    if row is None:
        raise not_found("No such session.")
    package = load(db, ctx, row.package_id, for_update=True)
    db.refresh(row, with_for_update=True)
    return row, package


def current(db: Session, ctx: StaffContext, *, trainer_id: uuid.UUID | None = None):
    """Packages still to train, oldest end first: what the trainers' lists
    show. Used-up packs are left out."""
    stmt = visible(ctx).where(
        PtPackage.cancelled_at.is_(None), PtPackage.end_date >= today_in_nepal()
    )
    if trainer_id is not None:
        stmt = stmt.where(PtPackage.trainer_id == trainer_id)
    packages = list(db.scalars(stmt.order_by(PtPackage.end_date, PtPackage.created_at)))
    counts = tallies(db, packages)
    return [p for p in packages if status_of(p, counts[p.id].used) in CURRENT], counts


def of_member(db: Session, member: Member) -> list[PtPackage]:
    return list(
        db.scalars(
            select(PtPackage)
            .where(PtPackage.member_id == member.id, PtPackage.gym_id == member.gym_id)
            .order_by(PtPackage.start_date.desc(), PtPackage.created_at.desc())
        )
    )


def _changed(db: Session, package: PtPackage) -> None:
    """Their page and app, and the Personal training screens."""
    live.member_changed(db, package.gym_id, package.member_id, package.branch_id)
    live.publish(db, gym_id=package.gym_id, kind=live.PT, branch_id=package.branch_id)


def _log(
    db: Session,
    ctx: StaffContext,
    package: PtPackage,
    action: str,
    changes: dict[str, Any],
    *,
    reason: str | None = None,
    request: Request | None = None,
) -> None:
    activity.staff_action(
        db,
        ctx.staff,
        action,
        entity="pt_package",
        entity_id=package.id,
        changes=changes,
        reason=reason,
        request=request,
    )


# --- selling ------------------------------------------------------------------


@dataclass
class SaleIn:
    plan_id: uuid.UUID
    trainer_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    price: int | None = None
    discount: int = 0
    payment: ms.PaymentIn | None = None


def sell(
    db: Session,
    ctx: StaffContext,
    member: Member,
    sale: SaleIn,
    config: GymSettings,
    *,
    request: Request | None = None,
) -> tuple[PtPackage, Payment | None]:
    """Personal training from one of the gym's PT plans, with one trainer,
    and the payment taken now if any."""
    plan = db.get(PtPlan, sale.plan_id)
    if plan is None or plan.gym_id != ctx.gym_id:
        raise AppError(422, "bad_plan", "That plan does not exist.")
    if not plan.is_active:
        raise AppError(422, "plan_hidden", "That plan is no longer offered.")
    trainer = _trainer(db, ctx, sale.trainer_id)
    branch = ms._branch_in_gym(db, ctx, sale.branch_id or member.home_branch_id)

    price = sale.price if sale.price is not None else plan.price
    if sale.discount < 0 or sale.discount > price:
        raise AppError(
            422, "bad_discount", "The discount can't be more than the price."
        )
    start = sale.start_date or today_in_nepal()
    end = sale.end_date or plan_end_date(
        start,
        months=plan.duration_months,
        days=plan.duration_days,
        calendar=config.plan_months,
    )
    if end < start:
        raise AppError(422, "bad_dates", "The end date is before the start date.")

    package = PtPackage(
        gym_id=ctx.gym_id,
        member_id=member.id,
        plan_id=plan.id,
        plan_name=plan.name,
        kind=plan.kind,
        sessions=plan.sessions,
        trainer_id=trainer.id,
        branch_id=branch.id,
        start_date=start,
        end_date=end,
        price=price,
        discount=sale.discount,
        created_by=ctx.staff.id,
    )
    db.add(package)
    db.flush()
    _changed(db, package)
    _log(
        db,
        ctx,
        package,
        "pt.sold",
        {
            "member_id": member.id,
            "plan_id": plan.id,
            "kind": plan.kind,
            "sessions": plan.sessions,
            **snapshot(package),
        },
        request=request,
    )

    payment = None
    if sale.payment is not None and sale.payment.amount > 0:
        payment = ms.record_payment(db, ctx, package, sale.payment, request=request)
    return package, payment


# --- changing -----------------------------------------------------------------


def _sessions_within(db: Session, package: PtPackage) -> None:
    """Moving the dates must not leave a session recorded outside them."""
    first, last = db.execute(
        select(func.min(PtSession.trained_on), func.max(PtSession.trained_on)).where(
            PtSession.package_id == package.id, PtSession.voided_at.is_(None)
        )
    ).one()
    if first is not None and (first < package.start_date or last > package.end_date):
        raise AppError(
            409,
            "sessions_outside",
            "Sessions were recorded outside those dates. Void them first.",
        )


def update(
    db: Session,
    ctx: StaffContext,
    package: PtPackage,
    changes: dict[str, Any],
    *,
    reason: str | None = None,
    request: Request | None = None,
) -> PtPackage:
    """Another trainer, or other dates (§18.3)."""
    if package.cancelled_at is not None:
        raise AppError(409, "pt_cancelled", "This personal training is cancelled.")
    before = snapshot(package)
    if changes.get("trainer_id") is not None:
        package.trainer_id = _trainer(db, ctx, changes["trainer_id"]).id
    for field in ("start_date", "end_date"):
        if changes.get(field) is not None:
            setattr(package, field, changes[field])
    if package.end_date < package.start_date:
        raise AppError(422, "bad_dates", "The end date is before the start date.")
    _sessions_within(db, package)

    diff = activity.diff(before, snapshot(package))
    if diff:
        _changed(db, package)
        _log(db, ctx, package, "pt.updated", diff, reason=reason, request=request)
    return package


def cancel(
    db: Session,
    ctx: StaffContext,
    package: PtPackage,
    reason: str,
    refund: ms.PaymentIn | None,
    *,
    request: Request | None = None,
) -> Payment | None:
    if package.cancelled_at is not None:
        raise AppError(
            409, "pt_cancelled", "This personal training is already cancelled."
        )
    refund_row = None
    if refund is not None and refund.amount > 0:
        refund_row = ms.record_payment(
            db, ctx, package, refund, kind=KIND_REFUND, request=request
        )
    before = snapshot(package)
    package.cancelled_at = utcnow()
    package.cancel_reason = reason
    _changed(db, package)
    _log(
        db,
        ctx,
        package,
        "pt.cancelled",
        activity.diff(before, snapshot(package)),
        reason=reason,
        request=request,
    )
    return refund_row


# --- sessions -----------------------------------------------------------------


def may_record(ctx: StaffContext, package: PtPackage) -> bool:
    """Its trainer, or anyone who sells personal training."""
    if ctx.can(Permission.PT_SELL):
        return True
    return ctx.can(Permission.PT_TRAIN) and package.trainer_id == ctx.staff.id


def _check_may_record(ctx: StaffContext, package: PtPackage) -> None:
    if not may_record(ctx, package):
        raise AppError(
            403,
            "permission_denied",
            "Only their trainer, or staff who sell personal training, can do this.",
            permission=Permission.PT_SELL.value,
        )


def record_session(
    db: Session,
    ctx: StaffContext,
    package: PtPackage,
    trained_on: dt.date | None,
    note: str | None,
    *,
    request: Request | None = None,
) -> PtSession:
    """`package` must have been loaded for update: two sessions recorded at
    once must not both fit in the last one a pack holds."""
    _check_may_record(ctx, package)
    if package.cancelled_at is not None:
        raise AppError(409, "pt_cancelled", "This personal training is cancelled.")
    today = today_in_nepal()
    day = trained_on or today
    if day > today:
        raise AppError(422, "future_date", "That day hasn't come yet.")
    if not package.start_date <= day <= package.end_date:
        raise AppError(
            422,
            "outside_dates",
            "That day is outside this personal training's dates.",
        )
    if package.kind == KIND_SESSIONS:
        used = db.scalar(
            select(func.count()).where(
                PtSession.package_id == package.id, PtSession.voided_at.is_(None)
            )
        )
        if package.sessions is not None and (used or 0) >= package.sessions:
            raise AppError(
                409, "pt_used_up", "Every session in this pack has been recorded."
            )
    row = PtSession(
        gym_id=package.gym_id,
        package_id=package.id,
        trained_on=day,
        trainer_id=package.trainer_id,
        recorded_by=ctx.staff.id,
        note=(note or "").strip() or None,
    )
    db.add(row)
    db.flush()
    _changed(db, package)
    # The note stays out of the log: it's about the member's body, and the
    # log outlives an erase (§5.6).
    _log(
        db,
        ctx,
        package,
        "pt.session_recorded",
        {"session_id": row.id, "trained_on": day, "trainer_id": row.trainer_id},
        request=request,
    )
    return row


def void_session(
    db: Session,
    ctx: StaffContext,
    row: PtSession,
    package: PtPackage,
    reason: str,
    *,
    request: Request | None = None,
) -> PtSession:
    _check_may_record(ctx, package)
    if row.voided_at is not None:
        raise AppError(409, "session_voided", "This session has already been voided.")
    row.voided_at = utcnow()
    row.voided_by = ctx.staff.id
    row.void_reason = reason
    _changed(db, package)
    _log(
        db,
        ctx,
        package,
        "pt.session_voided",
        {"session_id": row.id, "trained_on": row.trained_on},
        reason=reason,
        request=request,
    )
    return row
