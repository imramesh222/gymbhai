"""Personal training (PLAN.md §18.3): the gym's PT plans, selling them, the
trainers' clients and their sessions.

Money for it goes through the ordinary payments routes, with `pt_package_id`
in place of `membership_id`.
"""

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import idempotency
from app.api.deps import require, require_any
from app.api.presenters import payment_read, staff_names
from app.api.routes.members import load_member
from app.api.tenancy import StaffContext, for_gym, get_in_gym
from app.core.errors import AppError
from app.core.permissions import Permission
from app.core.time import today_in_nepal
from app.db.session import get_db
from app.models.gym import Gym
from app.models.member import Member
from app.models.training import KIND_SESSIONS, PtPackage, PtPlan
from app.schemas.money import VoidIn
from app.schemas.training import (
    PtCancelIn,
    PtPackageDetail,
    PtPackageRead,
    PtPackageUpdate,
    PtPlanCreate,
    PtPlanRead,
    PtPlanUpdate,
    PtSaleIn,
    PtSaleResult,
    PtSessionRead,
    SessionIn,
    Trainer,
)
from app.services import activity
from app.services import memberships as ms
from app.services import training as service

router = APIRouter(tags=["personal training"])

PLANS = require(Permission.SETUP_PLANS)
# Selling needs them, and so does their settings page.
SEE_PLANS = require_any(Permission.PT_SELL, Permission.SETUP_PLANS)
SELL = require(Permission.PT_SELL)
# A trainer on their own clients' packages, or the desk on anyone's: the
# service checks which (app/services/training.py).
SESSIONS = require_any(Permission.PT_TRAIN, Permission.PT_SELL)

PLAN_FIELDS = (
    "name",
    "kind",
    "sessions",
    "duration_months",
    "duration_days",
    "price",
    "is_active",
    "sort_order",
)
# A null sent for one of these clears it; for any other it changes nothing.
CLEARABLE = ("sessions", "duration_months", "duration_days")


def packages_read(
    db: Session, packages: Sequence[PtPackage], *, detail: bool = False
) -> list[PtPackageRead]:
    """Packages with what is computed about them: sessions, days and money;
    with `detail`, every session and payment too."""
    ids = [p.id for p in packages]
    logs = service.session_log(db, ids) if detail else {}
    paid = service.payments_by_package(db, ids) if detail else None
    counts = service.tallies(db, packages, paid)
    people = [p.trainer_id for p in packages]
    for rows in logs.values():
        people += [r.trainer_id for r in rows] + [r.recorded_by for r in rows]
    for payments in (paid or {}).values():
        people += [p.received_by for p in payments]
    names = staff_names(db, people)
    members = {
        row.id: row
        for row in db.execute(
            select(Member.id, Member.name, Member.member_code).where(
                Member.id.in_({p.member_id for p in packages})
            )
        )
    }
    today = today_in_nepal()
    reads = []
    for package in packages:
        tally = counts[package.id]
        read = (PtPackageDetail if detail else PtPackageRead).model_validate(package)
        read.member_name = members[package.member_id].name
        read.member_code = members[package.member_id].member_code
        read.trainer_name = names.get(package.trainer_id)
        read.status = service.status_of(package, tally.used, today)
        read.sessions_used = tally.used
        read.sessions_left = service.sessions_left(package, tally.used)
        read.days_left = (
            service.days_left(package, today) if read.status in service.CURRENT else 0
        )
        read.last_session_on = tally.last_on
        read.total = service.total_of(package)
        read.paid = tally.paid
        read.dues = tally.dues
        if isinstance(read, PtPackageDetail):
            read.session_log = [_session_read(row, names) for row in logs[package.id]]
            read.payments = [payment_read(p, names) for p in (paid or {})[package.id]]
        reads.append(read)
    return reads


def _session_read(row, names: dict[uuid.UUID, str]) -> PtSessionRead:
    read = PtSessionRead.model_validate(row)
    read.trainer_name = names.get(row.trainer_id)
    read.recorded_by_name = names.get(row.recorded_by) if row.recorded_by else None
    return read


def _details(db: Session, packages: Sequence[PtPackage]) -> list[PtPackageDetail]:
    reads = packages_read(db, packages, detail=True)
    return [read for read in reads if isinstance(read, PtPackageDetail)]


def _detail(db: Session, package: PtPackage) -> PtPackageDetail:
    return _details(db, [package])[0]


# --- plans (Settings → Personal training) --------------------------------------


@router.get("/pt/plans", response_model=list[PtPlanRead])
def list_plans(
    include_hidden: bool = False,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SEE_PLANS),
) -> list[PtPlan]:
    stmt = for_gym(select(PtPlan), PtPlan, ctx)
    if not include_hidden:
        stmt = stmt.where(PtPlan.is_active)
    return list(db.scalars(stmt.order_by(PtPlan.sort_order, PtPlan.created_at)))


@router.post(
    "/pt/plans", response_model=PtPlanRead, status_code=status.HTTP_201_CREATED
)
def create_plan(
    payload: PtPlanCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(PLANS),
) -> PtPlan:
    plan = PtPlan(gym_id=ctx.gym_id, **payload.model_dump())
    db.add(plan)
    db.flush()
    activity.staff_action(
        db,
        ctx.staff,
        "pt_plan.created",
        entity="pt_plan",
        entity_id=plan.id,
        changes=payload.model_dump(),
        request=request,
    )
    db.commit()
    return plan


@router.patch("/pt/plans/{pt_plan_id}", response_model=PtPlanRead)
def update_plan(
    pt_plan_id: uuid.UUID,
    payload: PtPlanUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(PLANS),
) -> PtPlan:
    plan = get_in_gym(db, PtPlan, pt_plan_id, ctx, message="No such plan.")
    changes = payload.model_dump(exclude_unset=True)
    before = {name: getattr(plan, name) for name in PLAN_FIELDS}
    # Switching between months and days replaces the other; monthly
    # training counts no sessions.
    if changes.get("duration_months") is not None:
        changes["duration_days"] = None
    elif changes.get("duration_days") is not None:
        changes["duration_months"] = None
    if changes.get("kind") == "monthly":
        changes["sessions"] = None
    for name in PLAN_FIELDS:
        if name in changes:
            if changes[name] is None and name not in CLEARABLE:
                continue
            setattr(plan, name, changes[name])
    if plan.duration_months is None and plan.duration_days is None:
        raise AppError(422, "needs_duration", "Give a duration in months or in days.")
    if (plan.kind == KIND_SESSIONS) != (plan.sessions is not None):
        raise AppError(
            422, "pack_sessions", "A pack of sessions says how many; monthly doesn't."
        )
    diff = activity.diff(before, {name: getattr(plan, name) for name in PLAN_FIELDS})
    if diff:
        activity.staff_action(
            db,
            ctx.staff,
            "pt_plan.updated",
            entity="pt_plan",
            entity_id=plan.id,
            changes=diff,
            request=request,
        )
    db.commit()
    return plan


# --- trainers and their clients ------------------------------------------------


@router.get("/pt/trainers", response_model=list[Trainer])
def list_trainers(
    db: Session = Depends(get_db), ctx: StaffContext = Depends(SELL)
) -> list[Trainer]:
    """Staff who train members, and the owner: whom a package can be given to."""
    return [Trainer(id=s.id, name=s.name) for s in service.trainers(db, ctx.gym_id)]


@router.get("/pt/clients", response_model=list[PtPackageRead])
def my_clients(
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.PT_TRAIN)),
) -> list[PtPackageRead]:
    """The caller's own clients still to train: upcoming and active."""
    packages, _ = service.current(db, ctx, trainer_id=ctx.staff.id)
    return packages_read(db, packages)


@router.get("/pt/packages", response_model=list[PtPackageRead])
def all_packages(
    trainer_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SELL),
) -> list[PtPackageRead]:
    """Every trainer's clients still to train, or one trainer's."""
    packages, _ = service.current(db, ctx, trainer_id=trainer_id)
    return packages_read(db, packages)


# --- a member's personal training ---------------------------------------------


@router.get("/members/{member_id}/pt", response_model=list[PtPackageDetail])
def member_packages(
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_VIEW)),
) -> list[PtPackageDetail]:
    """The profile's Personal training tab: every package, sessions and money."""
    member = load_member(db, ctx, member_id)
    return _details(db, service.of_member(db, member))


@router.post(
    "/members/{member_id}/pt",
    response_model=PtSaleResult,
    status_code=status.HTTP_201_CREATED,
)
def sell(
    member_id: uuid.UUID,
    payload: PtSaleIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SELL),
) -> PtSaleResult:
    """Personal training with a trainer, and the payment taken now if any."""
    idem = idempotency.begin(db, ctx, request, payload)
    member = load_member(db, ctx, member_id)
    if member.is_archived:
        raise AppError(409, "member_archived", "Restore this member first.")
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    payment = None
    if payload.payment is not None:
        payment = ms.PaymentIn(**payload.payment.model_dump())
    package, paid = service.sell(
        db,
        ctx,
        member,
        service.SaleIn(**payload.model_dump(exclude={"payment"}), payment=payment),
        gym.config,
        request=request,
    )
    answer = PtSaleResult(
        package=_detail(db, package),
        payment=payment_read(paid, {ctx.staff.id: ctx.staff.name}) if paid else None,
    )
    idem.finish(answer)
    db.commit()
    return answer


@router.patch("/pt/packages/{package_id}", response_model=PtPackageDetail)
def update_package(
    package_id: uuid.UUID,
    payload: PtPackageUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SELL),
) -> PtPackageDetail:
    package = service.load(db, ctx, package_id, for_update=True)
    service.update(
        db,
        ctx,
        package,
        payload.model_dump(exclude_unset=True, exclude={"reason"}),
        reason=payload.reason,
        request=request,
    )
    db.commit()
    return _detail(db, package)


@router.post("/pt/packages/{package_id}/cancel", response_model=PtPackageDetail)
def cancel_package(
    package_id: uuid.UUID,
    payload: PtCancelIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SELL),
) -> PtPackageDetail:
    package = service.load(db, ctx, package_id, for_update=True)
    refund = ms.PaymentIn(**payload.refund.model_dump()) if payload.refund else None
    service.cancel(db, ctx, package, payload.reason, refund, request=request)
    db.commit()
    return _detail(db, package)


@router.post(
    "/pt/packages/{package_id}/sessions",
    response_model=PtPackageDetail,
    status_code=status.HTTP_201_CREATED,
)
def record_session(
    package_id: uuid.UUID,
    payload: SessionIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SESSIONS),
) -> PtPackageDetail:
    """One session trained: once, however often Record is tapped."""
    idem = idempotency.begin(db, ctx, request, payload)
    package = service.load(db, ctx, package_id, for_update=True)
    service.record_session(
        db, ctx, package, payload.trained_on, payload.note, request=request
    )
    answer = _detail(db, package)
    idem.finish(answer)
    db.commit()
    return answer


@router.post("/pt/sessions/{pt_session_id}/void", response_model=PtPackageDetail)
def void_session(
    pt_session_id: uuid.UUID,
    payload: VoidIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SESSIONS),
) -> PtPackageDetail:
    row, package = service.load_session(db, ctx, pt_session_id)
    service.void_session(db, ctx, row, package, payload.reason, request=request)
    db.commit()
    return _detail(db, package)
