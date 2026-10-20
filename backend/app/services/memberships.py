"""Selling, renewing and editing memberships, and the money on them.

The rules that matter (PLAN.md §5, §6):

* Status is computed from dates, freezes and cancelled_at — never stored.
* Renewing early starts the day after the current membership ends, so early
  renewers lose nothing; after a lapse it starts today.
* Price, discount and admission fee are copied onto the membership at sale.
* Dues = price − discount + admission fee − payments + refunds (voided
  payments count for nothing; a cancelled membership owes nothing more).
* Payments are recorded here for personal training too (§18.3): the same
  rules, against the package's own price, never a membership's dues.
* A family or couple plan (§19.1) is one membership each, tied by a
  membership group: the payer's carries the price and every payment, the
  others carry nothing, and the door counts the payer's dues for everyone.
* Every change goes to activity_log with before and after.
"""

import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any

from fastapi import Request
from sqlalchemy import ColumnElement, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.tenancy import StaffContext, get_in_gym
from app.core.calendar import plan_end_date
from app.core.errors import AppError
from app.core.gym_settings import GymSettings
from app.core.permissions import Permission
from app.core.time import today_in_nepal, utcnow
from app.models.gym import Branch
from app.models.member import Member
from app.models.member_app import LET_IN, CheckIn
from app.models.membership import (
    SOURCE_DESK,
    Membership,
    MembershipFreeze,
    MembershipGroup,
)
from app.models.payment import KIND_PAYMENT, KIND_REFUND, Payment
from app.models.plan import Plan, PlanBranch
from app.models.training import PtPackage
from app.services import activity, counters, live, tax

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


def owed(target: Membership | PtPackage, payments: Iterable[Payment]) -> int:
    """Still to pay on a membership, or on personal training (§18.3): its
    price less the discount, with no admission fee."""
    if isinstance(target, Membership):
        return dues_of(target, payments)
    if target.cancelled_at is not None:
        return 0
    return target.price - target.discount - net_paid(payments)


def snapshot(membership: Membership) -> dict[str, Any]:
    return {field: getattr(membership, field) for field in TRACKED}


# --- locking ------------------------------------------------------------------


def lock_member(db: Session, member: Member) -> None:
    """Serialise sales and renewals for one member until the transaction ends.

    Two desks (or the desk and an app approval) renewing at once would both
    read the same "renewal starts on" and "first membership?", and sell two
    overlapping memberships, each with the admission fee.
    """
    db.execute(select(Member.id).where(Member.id == member.id).with_for_update())


def lock_members(db: Session, members: Sequence[Member]) -> None:
    """lock_member for everyone on one sale (§19.1), in id order, so two desks
    selling to overlapping families queue up instead of deadlocking."""
    db.execute(
        select(Member.id)
        .where(Member.id.in_([m.id for m in members]))
        .order_by(Member.id)
        .with_for_update()
    )


def lock_transaction_ref(db: Session, gym_id: uuid.UUID, ref: str) -> None:
    """Serialise uses of one transaction ID in a gym until the transaction ends.

    The unique index only covers payments; this also covers a desk payment
    racing a member's pending app request with the same ID.
    """
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"txref:{gym_id}:{ref}"},
    )


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


def payments_on(db: Session, target: Membership | PtPackage) -> list[Payment]:
    if isinstance(target, Membership):
        column = Payment.membership_id
    else:
        column = Payment.pt_package_id
    return list(
        db.scalars(select(Payment).where(column == target.id).order_by(Payment.paid_at))
    )


def payments_in_branches(branches: Iterable[uuid.UUID]) -> ColumnElement[bool]:
    """Payments for a membership, for personal training, or for a sale at the
    desk (§20.1), at these branches."""
    from app.models.shop import ProductSale

    branches = list(branches)
    return or_(
        Payment.membership_id.in_(
            select(Membership.id).where(Membership.branch_id.in_(branches))
        ),
        Payment.pt_package_id.in_(
            select(PtPackage.id).where(PtPackage.branch_id.in_(branches))
        ),
        Payment.sale_id.in_(
            select(ProductSale.id).where(ProductSale.branch_id.in_(branches))
        ),
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


# --- family and couple plans (PLAN.md §19.1) ------------------------------------


def group_memberships(db: Session, group_id: uuid.UUID) -> list[Membership]:
    """Everyone's membership on one family or couple plan, cancelled ones too."""
    return list(
        db.scalars(
            select(Membership)
            .where(Membership.group_id == group_id)
            .order_by(Membership.created_at, Membership.id)
        )
    )


def payer_membership(db: Session, group: MembershipGroup) -> Membership | None:
    return db.scalars(
        select(Membership).where(
            Membership.group_id == group.id,
            Membership.member_id == group.payer_member_id,
        )
    ).first()


def is_payer(db: Session, membership: Membership) -> bool:
    """True for a membership of one's own, or the one that pays for a group."""
    if membership.group_id is None:
        return True
    group = db.get(MembershipGroup, membership.group_id)
    return group is None or group.payer_member_id == membership.member_id


def group_dues_for(
    db: Session, memberships: Sequence[Membership]
) -> dict[uuid.UUID, int]:
    """By member: what the family or couple plans they're on still owe, where
    someone else pays. Not theirs to pay, but the door's dues rule counts it.
    No query at all unless one of these memberships is on such a plan."""
    groups = {m.group_id for m in memberships if m.group_id and m.cancelled_at is None}
    if not groups:
        return {}
    payers = list(
        db.scalars(
            select(Membership)
            .join(MembershipGroup, MembershipGroup.id == Membership.group_id)
            .where(
                Membership.group_id.in_(groups),
                Membership.member_id == MembershipGroup.payer_member_id,
            )
        )
    )
    paid: dict[uuid.UUID, list[Payment]] = defaultdict(list)
    for payment in payments_for(db, [m.id for m in payers]):
        paid[payment.membership_id].append(payment)  # type: ignore[index]
    owing = {m.group_id: (m.member_id, dues_of(m, paid[m.id])) for m in payers}
    found: dict[uuid.UUID, int] = defaultdict(int)
    counted: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for m in memberships:
        if m.group_id not in owing or m.cancelled_at is not None:
            continue
        payer, dues = owing[m.group_id]
        if payer == m.member_id or (m.member_id, m.group_id) in counted:
            continue
        counted.add((m.member_id, m.group_id))
        found[m.member_id] += dues
    return dict(found)


def renewal_group(db: Session, member: Member) -> list[Member] | None:
    """Who a payer renews their family or couple plan with from the app: the
    others still on the plan of their latest membership. None when that
    membership is someone else's to pay, or their own alone."""
    latest = db.scalars(
        select(Membership)
        .where(
            Membership.member_id == member.id,
            Membership.gym_id == member.gym_id,
            Membership.cancelled_at.is_(None),
        )
        .order_by(Membership.end_date.desc(), Membership.created_at.desc())
    ).first()
    if latest is None or latest.group_id is None or not is_payer(db, latest):
        return None
    ids = [
        m.member_id
        for m in group_memberships(db, latest.group_id)
        if m.cancelled_at is None and m.member_id != member.id
    ]
    if not ids:
        return []
    return list(
        db.scalars(
            select(Member)
            .where(Member.id.in_(ids), Member.is_archived.is_(False))
            .order_by(Member.name)
        )
    )


def _people(
    db: Session,
    ctx: StaffContext,
    payer: Member,
    plan: Plan,
    ids: Sequence[uuid.UUID],
) -> list[Member]:
    """The others a family or couple plan is sold to, checked."""
    if not ids:
        return []
    if plan.seats < 2:
        raise AppError(422, "plan_for_one", "This plan is for one person.")
    if len(set(ids)) != len(ids) or payer.id in ids:
        raise AppError(422, "same_person_twice", "Choose each person once.")
    if len(ids) > plan.seats - 1:
        raise AppError(
            422,
            "too_many_people",
            f"This plan covers {plan.seats} people.",
            seats=plan.seats,
        )
    people = []
    for member_id in ids:
        other = get_in_gym(
            db,
            Member,
            member_id,
            ctx,
            branch_column=Member.home_branch_id,
            message="No such member.",
        )
        if other.is_archived:
            raise AppError(
                409, "member_archived", f"{other.name} is archived. Restore them first."
            )
        people.append(other)
    return people


# --- visit packs (PLAN.md §16.4, 9.3) ---------------------------------------------


def visits_used_expression():
    """Visits let in on a membership, as a correlated SQL expression."""
    return (
        select(func.count())
        .where(CheckIn.membership_id == Membership.id, CheckIn.result.in_(LET_IN))
        .correlate(Membership)
        .scalar_subquery()
    )


def usable():
    """Not a visit pack with every visit used: in SQL, beside the dates."""
    return or_(
        Membership.visit_limit.is_(None),
        visits_used_expression() < Membership.visit_limit,
    )


def visits_used(db: Session, memberships: Sequence[Membership]) -> dict[uuid.UUID, int]:
    """Visits used on each visit pack among these: one query, none without packs."""
    ids = [m.id for m in memberships if m.visit_limit is not None]
    if not ids:
        return {}
    return dict(
        db.execute(
            select(CheckIn.membership_id, func.count())
            .where(CheckIn.membership_id.in_(ids), CheckIn.result.in_(LET_IN))
            .group_by(CheckIn.membership_id)
        ).all()
    )


def renewal_start(db: Session, member: Member, today: dt.date | None = None) -> dt.date:
    """The day after the current membership ends, or today after a lapse (or
    once a visit pack is used up)."""
    today = today or today_in_nepal()
    latest_end = db.scalar(
        select(func.max(Membership.end_date)).where(
            Membership.member_id == member.id,
            Membership.gym_id == member.gym_id,
            Membership.cancelled_at.is_(None),
            usable(),
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
    target: Membership | PtPackage,
    payment: PaymentIn,
    *,
    kind: str = KIND_PAYMENT,
    request: Request | None = None,
    check_permission: bool = True,
) -> Payment:
    """Record money received for (or refunded on) a membership, or on
    personal training (§18.3).

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

    training = isinstance(target, PtPackage)
    # Locked and re-read: two payments at once must not both fit in the dues.
    db.refresh(target, with_for_update=True)
    existing = payments_on(db, target)
    if kind == KIND_PAYMENT:
        if target.cancelled_at is not None:
            if training:
                raise AppError(
                    409, "pt_cancelled", "This personal training is cancelled."
                )
            raise AppError(409, "membership_cancelled", "This membership is cancelled.")
        due = owed(target, existing)
        if payment.amount > due:
            raise AppError(
                422,
                "overpayment",
                "That is more than is owed on this personal training."
                if training
                else "That is more than is owed on this membership.",
                owed=due,
            )
    elif payment.amount > net_paid(existing):
        raise AppError(422, "refund_too_large", "You can't refund more than was paid.")

    ref = (payment.transaction_ref or "").strip() or None
    if ref:
        lock_transaction_ref(db, ctx.gym_id, ref)
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
        member_id=target.member_id,
        membership_id=None if training else target.id,
        pt_package_id=target.id if training else None,
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
    # A VAT-registered gym's invoice, or a refund's credit note (§20.4).
    tax.on_payment(db, row, ctx.staff.id)

    live.member_changed(db, ctx.gym_id, target.member_id, target.branch_id)
    if training:
        live.publish(db, gym_id=ctx.gym_id, kind=live.PT, branch_id=target.branch_id)
    activity.staff_action(
        db,
        ctx.staff,
        "payment.recorded" if kind == KIND_PAYMENT else "refund.recorded",
        entity="payment",
        entity_id=row.id,
        changes={
            ("pt_package_id" if training else "membership_id"): target.id,
            "member_id": target.member_id,
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
    # A family or couple plan (§19.1): the others it covers; the member it is
    # sold to pays.
    with_member_ids: list[uuid.UUID] = dataclass_field(default_factory=list)


def _new_membership(
    db: Session,
    ctx: StaffContext,
    member: Member,
    plan: Plan,
    *,
    branch: Branch,
    start: dt.date,
    end: dt.date,
    price: int,
    discount: int,
    admission: int,
    source: str,
    group: MembershipGroup | None,
    renewal: bool,
    request: Request | None,
) -> Membership:
    membership = Membership(
        gym_id=ctx.gym_id,
        member_id=member.id,
        plan_id=plan.id,
        plan_name=plan.name,
        visit_limit=plan.visit_limit,
        access_hours=plan.access_hours,
        branch_id=branch.id,
        start_date=start,
        end_date=end,
        price=price,
        discount=discount,
        admission_fee=admission,
        created_by=ctx.staff.id,
        source=source,
        group_id=group.id if group else None,
        classes=plan.classes,
        class_type_ids=plan.class_type_ids,
    )
    db.add(membership)
    db.flush()
    live.member_changed(db, ctx.gym_id, member.id, branch.id)
    changes: dict[str, Any] = {"member_id": member.id, "renewal": renewal}
    if group is not None:
        changes["group_id"] = group.id
        changes["paid_by"] = group.payer_member_id
    activity.staff_action(
        db,
        ctx.staff,
        "membership.created",
        entity="membership",
        entity_id=membership.id,
        changes={**changes, **snapshot(membership)},
        request=request,
    )
    return membership


def _sale_branch(
    db: Session, ctx: StaffContext, plan: Plan, branch_id: uuid.UUID
) -> Branch:
    branch = _branch_in_gym(db, ctx, branch_id)
    if not plan_covers_branch(db, plan, branch.id):
        raise AppError(
            422, "plan_not_at_branch", "That plan isn't sold at this branch."
        )
    return branch


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
    """A new membership or a renewal, with an optional payment taken now.

    A family or couple plan sells one membership to each person, all made
    here; the returned one is the payer's, which carries the money."""
    plan = db.get(Plan, sale.plan_id)
    if plan is None or plan.gym_id != ctx.gym_id:
        raise AppError(422, "bad_plan", "That plan does not exist.")
    others = _people(db, ctx, member, plan, sale.with_member_ids)
    lock_members(db, [member, *others])
    if not plan.is_active:
        raise AppError(422, "plan_hidden", "That plan is no longer offered.")

    branch = _sale_branch(db, ctx, plan, sale.branch_id or member.home_branch_id)

    price = sale.price if sale.price is not None else plan.price
    if price is None:
        raise AppError(
            422, "plan_has_no_price", "Set a price for this plan, or enter one here."
        )
    first = is_first_membership(db, member)
    newcomers = [first] + [is_first_membership(db, o) for o in others]
    # The plan's fee for each person on their first membership, all on the
    # payer's (§19.1); the desk can change it.
    admission = (
        sale.admission_fee
        if sale.admission_fee is not None
        else plan.admission_fee * sum(newcomers)
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

    group = None
    if plan.seats > 1:
        group = MembershipGroup(
            gym_id=ctx.gym_id,
            plan_id=plan.id,
            payer_member_id=member.id,
            seats=plan.seats,
            created_by=ctx.staff.id,
        )
        db.add(group)
        db.flush()
    membership = _new_membership(
        db,
        ctx,
        member,
        plan,
        branch=branch,
        start=start,
        end=end,
        price=price,
        discount=sale.discount,
        admission=admission,
        source=sale.source,
        group=group,
        renewal=not first,
        request=request,
    )
    for other, other_first in zip(others, newcomers[1:], strict=True):
        # Everyone on the sale's dates when the desk gave them; otherwise each
        # renews from the end of their own membership, losing no days.
        other_start = sale.start_date or renewal_start(db, other)
        other_end = (
            end
            if sale.start_date is not None
            else plan_end_date(
                other_start,
                months=plan.duration_months,
                days=plan.duration_days,
                calendar=config.plan_months,
            )
        )
        _new_membership(
            db,
            ctx,
            other,
            plan,
            branch=_sale_branch(db, ctx, plan, sale.branch_id or other.home_branch_id),
            start=other_start,
            end=other_end,
            price=0,
            discount=0,
            admission=0,
            source=sale.source,
            group=group,
            renewal=not other_first,
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
    live.member_changed(db, ctx.gym_id, membership.member_id, membership.branch_id)
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
    group = (
        db.get(MembershipGroup, membership.group_id) if membership.group_id else None
    )
    new_plan_id = changes.get("plan_id")
    changing_plan = new_plan_id is not None and new_plan_id != membership.plan_id
    if group is not None and group.payer_member_id != membership.member_id:
        if changing_plan or any(
            changes.get(f) is not None for f in ("price", "discount", "admission_fee")
        ):
            raise AppError(
                422,
                "money_on_payer",
                "The plan and its price are on the membership of whoever pays.",
            )
    explicit_end = changes.get("end_date") is not None

    plan = None
    if changing_plan:
        plan = db.get(Plan, new_plan_id)
        if plan is None or plan.gym_id != ctx.gym_id:
            raise AppError(422, "bad_plan", "That plan does not exist.")
        if group is not None and plan.seats != group.seats:
            raise AppError(
                422,
                "plan_people_differ",
                f"Choose a plan for {group.seats} people.",
                seats=group.seats,
            )
        if group is None and plan.seats > 1:
            raise AppError(
                422,
                "plan_for_group",
                "That plan is for several people. Sell it to them instead.",
            )
        membership.plan_id = plan.id
        membership.plan_name = plan.name
        # The new plan's classes come with it (§19.4).
        membership.classes = plan.classes
        membership.class_type_ids = plan.class_type_ids
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
    if plan is not None and group is not None:
        # The payer's new plan is everyone's: same end date if the desk gave
        # one, else each from their own start.
        group.plan_id = plan.id
        for other in group_memberships(db, group.id):
            if other.id == membership.id or other.cancelled_at is not None:
                continue
            other_before = snapshot(other)
            other.plan_id = plan.id
            other.plan_name = plan.name
            other.classes = plan.classes
            other.class_type_ids = plan.class_type_ids
            other.end_date = (
                membership.end_date
                if explicit_end
                else plan_end_date(
                    other.start_date,
                    months=plan.duration_months,
                    days=plan.duration_days,
                    calendar=config.plan_months,
                )
            )
            if other.end_date < other.start_date:
                raise AppError(
                    422, "bad_dates", "The end date is before someone's start date."
                )
            _log_edit(
                db,
                ctx,
                other,
                "membership.updated",
                other_before,
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


def extend_all_selection(
    db: Session, ctx: StaffContext, branch_id: uuid.UUID | None = None
):
    """The memberships Extend everyone would change: current and upcoming."""
    stmt = select(Membership).where(
        Membership.gym_id == ctx.gym_id,
        Membership.cancelled_at.is_(None),
        Membership.end_date >= today_in_nepal(),
    )
    if branch_id is not None:
        _branch_in_gym(db, ctx, branch_id)
        stmt = stmt.where(Membership.branch_id == branch_id)
    elif ctx.branch_ids is not None:
        stmt = stmt.where(Membership.branch_id.in_(ctx.branch_ids))
    return stmt


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
    stmt = extend_all_selection(db, ctx, branch_id)
    batch = uuid.uuid4()
    count = 0
    # Locked in id order, so two runs at once queue up instead of deadlocking.
    for membership in db.scalars(stmt.order_by(Membership.id).with_for_update()):
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
    cancelling = [membership]
    group = (
        db.get(MembershipGroup, membership.group_id) if membership.group_id else None
    )
    if group is not None and group.payer_member_id == membership.member_id:
        # Whoever pays cancels the plan for everyone on it (§19.1).
        cancelling += [
            m
            for m in group_memberships(db, group.id)
            if m.id != membership.id and m.cancelled_at is None
        ]
    now = utcnow()
    for row in cancelling:
        before = snapshot(row)
        row.cancelled_at = now
        row.cancel_reason = reason
        _log_edit(
            db,
            ctx,
            row,
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
    if membership.group_id is not None and is_payer(db, membership):
        if any(
            m.id != membership.id and m.cancelled_at is None
            for m in group_memberships(db, membership.group_id)
        ):
            raise AppError(
                409, "group_has_people", "Remove the others on this plan first."
            )
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
    live.member_changed(db, ctx.gym_id, membership.member_id, membership.branch_id)
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


def add_to_group(
    db: Session,
    ctx: StaffContext,
    group: MembershipGroup,
    member: Member,
    start_date: dt.date | None,
    *,
    request: Request | None = None,
) -> Membership:
    """Someone joins a family or couple plan with a free place (§19.1): from
    today, or a day given, to the payer's end date; the price doesn't change.

    `group` must be locked: two desks filling the last place at once would
    otherwise both fit."""
    payer = payer_membership(db, group)
    if payer is None or payer.cancelled_at is not None:
        raise AppError(409, "membership_cancelled", "This plan is cancelled.")
    on_it = [m for m in group_memberships(db, group.id) if m.cancelled_at is None]
    if any(m.member_id == member.id for m in on_it):
        raise AppError(
            409, "already_on_plan", f"{member.name} is already on this plan."
        )
    if len(on_it) >= group.seats:
        raise AppError(
            409, "group_full", f"This plan covers {group.seats} people, and has them."
        )
    if member.is_archived:
        raise AppError(
            409, "member_archived", f"{member.name} is archived. Restore them first."
        )
    lock_member(db, member)
    start = start_date or max(today_in_nepal(), payer.start_date)
    if start > payer.end_date:
        raise AppError(422, "bad_dates", "The plan ends before then.")
    plan = db.get(Plan, payer.plan_id) if payer.plan_id else None
    if plan is None:
        raise AppError(422, "bad_plan", "That plan does not exist.")
    return _new_membership(
        db,
        ctx,
        member,
        plan,
        branch=_sale_branch(db, ctx, plan, member.home_branch_id),
        start=start,
        end=payer.end_date,
        price=0,
        discount=0,
        admission=0,
        source=SOURCE_DESK,
        group=group,
        renewal=not is_first_membership(db, member),
        request=request,
    )
