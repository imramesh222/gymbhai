"""Members: creating them, and where each one stands today.

A member's state is derived from their memberships, never stored:

* active   — a membership covers today and it is not frozen today
* frozen   — a membership covers today and a freeze covers today
* upcoming — nothing covers today, but a membership starts later
* expired  — every membership has ended
* none     — never had one

"Valid until" follows back-to-back renewals: renewing early queues the new
membership the day after the current one ends, and the member's days left run
to the end of the chain.
"""

import datetime as dt
import secrets
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from fastapi import Request
from sqlalchemy import Select, and_, case, exists, func, or_, select
from sqlalchemy.orm import Session

from app.api.tenancy import StaffContext
from app.core.errors import AppError
from app.core.gym_settings import GymSettings
from app.core.time import today_in_nepal
from app.models.gym import Branch
from app.models.member import Member
from app.models.membership import Membership, MembershipFreeze
from app.models.payment import KIND_PAYMENT, Payment
from app.services import activity, counters
from app.services import memberships as ms

NONE = "none"
STATUSES = (ms.ACTIVE, ms.FROZEN, ms.UPCOMING, ms.EXPIRED, NONE)

# Fields shown in the History of a member (§5.6).
TRACKED = (
    "name",
    "phone",
    "email",
    "gender",
    "date_of_birth",
    "address",
    "emergency_contact",
    "home_branch_id",
    "joined_on",
    "notes",
    "app_access",
    "is_archived",
    "photo_key",
    "qr_version",
    "card_token",
)


def new_qr_secret() -> str:
    return secrets.token_hex(32)


def new_card_token() -> str:
    return secrets.token_urlsafe(18)


def snapshot(member: Member) -> dict[str, Any]:
    return {name: getattr(member, name) for name in TRACKED}


def _branch(db: Session, ctx: StaffContext, branch_id: uuid.UUID) -> Branch:
    branch = db.get(Branch, branch_id)
    if branch is None or branch.gym_id != ctx.gym_id:
        raise AppError(422, "bad_branch", "That branch does not exist.")
    if not ctx.can_access_branch(branch.id):
        raise AppError(403, "branch_denied", "You don't work at that branch.")
    return branch


def default_branch_id(db: Session, ctx: StaffContext) -> uuid.UUID:
    stmt = select(Branch.id).where(Branch.gym_id == ctx.gym_id, Branch.is_active)
    if ctx.branch_ids is not None:
        stmt = stmt.where(Branch.id.in_(ctx.branch_ids))
    branch_id = db.scalar(stmt.order_by(Branch.created_at).limit(1))
    if branch_id is None:
        raise AppError(422, "no_branch", "Add a branch first.")
    return branch_id


def create(
    db: Session,
    ctx: StaffContext,
    data: dict[str, Any],
    config: GymSettings,
    *,
    request: Request | None = None,
) -> Member:
    branch_id = data.pop("home_branch_id", None) or default_branch_id(db, ctx)
    _branch(db, ctx, branch_id)
    number = counters.next_value(db, ctx.gym_id, counters.MEMBER_CODE)
    member = Member(
        gym_id=ctx.gym_id,
        home_branch_id=branch_id,
        member_code=f"{config.member_code_prefix}-{number:04d}",
        joined_on=data.pop("joined_on", None) or today_in_nepal(),
        qr_secret=new_qr_secret(),
        card_token=new_card_token(),
        **data,
    )
    db.add(member)
    db.flush()
    activity.staff_action(
        db,
        ctx.staff,
        "member.created",
        entity="member",
        entity_id=member.id,
        changes={"member_code": member.member_code, **snapshot(member)},
        request=request,
    )
    return member


def update(
    db: Session,
    ctx: StaffContext,
    member: Member,
    changes: dict[str, Any],
    *,
    action: str = "member.updated",
    reason: str | None = None,
    request: Request | None = None,
) -> Member:
    if changes.get("home_branch_id") is not None:
        _branch(db, ctx, changes["home_branch_id"])
    before = snapshot(member)
    for name, value in changes.items():
        setattr(member, name, value)
    if member.phone != before["phone"] or member.email != before["email"]:
        # The old phone or email stops working at once, and devices sign out.
        from app.services.member_auth import sign_out_everywhere

        sign_out_everywhere(db, member.id)
    diff = activity.diff(before, snapshot(member))
    if diff:
        activity.staff_action(
            db,
            ctx.staff,
            action,
            entity="member",
            entity_id=member.id,
            changes=diff,
            reason=reason,
            request=request,
        )
    return member


def same_phone(
    db: Session, gym_id: uuid.UUID, phone: str, exclude: uuid.UUID | None = None
) -> list[Member]:
    """Members already on file with this phone: families often share one (§5.5)."""
    stmt = select(Member).where(
        Member.gym_id == gym_id, Member.phone == phone, Member.is_archived.is_(False)
    )
    if exclude is not None:
        stmt = stmt.where(Member.id != exclude)
    return list(db.scalars(stmt.order_by(Member.name)))


# --- where a member stands ------------------------------------------------------


@dataclass
class MemberState:
    status: str
    current: Membership | None = None
    valid_until: dt.date | None = None
    days_left: int = 0
    dues: int = 0
    memberships: list[Membership] = field(default_factory=list)


def state_of(
    memberships: Sequence[Membership],
    freezes: dict[uuid.UUID, list[MembershipFreeze]],
    payments: dict[uuid.UUID, list[Payment]],
    today: dt.date | None = None,
) -> MemberState:
    today = today or today_in_nepal()
    live = sorted(
        (m for m in memberships if m.cancelled_at is None), key=lambda m: m.start_date
    )
    dues = sum(ms.dues_of(m, payments.get(m.id, [])) for m in memberships)

    def chain_end(first: Membership) -> dt.date:
        end = first.end_date
        for m in live:
            if m.start_date <= end + dt.timedelta(days=1) and m.end_date > end:
                end = m.end_date
        return end

    covering = [m for m in live if m.start_date <= today <= m.end_date]
    if covering:
        current = covering[-1]
        frozen = any(
            f.from_date <= today <= f.to_date for f in freezes.get(current.id, [])
        )
        until = chain_end(covering[0])
        return MemberState(
            status=ms.FROZEN if frozen else ms.ACTIVE,
            current=current,
            valid_until=until,
            days_left=(until - today).days + 1,
            dues=dues,
            memberships=list(memberships),
        )
    upcoming = [m for m in live if m.start_date > today]
    if upcoming:
        return MemberState(
            status=ms.UPCOMING,
            current=upcoming[0],
            valid_until=chain_end(upcoming[0]),
            dues=dues,
            memberships=list(memberships),
        )
    if live:
        last = max(live, key=lambda m: m.end_date)
        return MemberState(
            status=ms.EXPIRED,
            current=last,
            valid_until=last.end_date,
            dues=dues,
            memberships=list(memberships),
        )
    return MemberState(status=NONE, dues=dues, memberships=list(memberships))


def states_for(
    db: Session, members: Sequence[Member], today: dt.date | None = None
) -> dict[uuid.UUID, MemberState]:
    """Every member's state in three queries, however many members."""
    ids = [m.id for m in members]
    if not ids:
        return {}
    rows = list(db.scalars(select(Membership).where(Membership.member_id.in_(ids))))
    by_member: dict[uuid.UUID, list[Membership]] = defaultdict(list)
    for row in rows:
        by_member[row.member_id].append(row)
    membership_ids = [r.id for r in rows]
    freezes: dict[uuid.UUID, list[MembershipFreeze]] = defaultdict(list)
    for f in ms.freezes_for(db, membership_ids):
        freezes[f.membership_id].append(f)
    payments: dict[uuid.UUID, list[Payment]] = defaultdict(list)
    for p in ms.payments_for(db, membership_ids):
        payments[p.membership_id].append(p)  # type: ignore[index]
    return {m.id: state_of(by_member[m.id], freezes, payments, today) for m in members}


def state(db: Session, member: Member) -> MemberState:
    return states_for(db, [member])[member.id]


# --- search and filters (SQL) ---------------------------------------------------


def _covering_today(today: dt.date):
    return and_(
        Membership.member_id == Member.id,
        Membership.cancelled_at.is_(None),
        Membership.start_date <= today,
        Membership.end_date >= today,
    )


def _frozen_today(today: dt.date):
    return exists().where(
        MembershipFreeze.membership_id == Membership.id,
        MembershipFreeze.from_date <= today,
        MembershipFreeze.to_date >= today,
    )


def status_filter(status: str, today: dt.date):
    covering = exists().where(_covering_today(today))
    covering_frozen = exists().where(_covering_today(today), _frozen_today(today))
    covering_open = exists().where(_covering_today(today), ~_frozen_today(today))
    future = exists().where(
        Membership.member_id == Member.id,
        Membership.cancelled_at.is_(None),
        Membership.start_date > today,
    )
    any_live = exists().where(
        Membership.member_id == Member.id, Membership.cancelled_at.is_(None)
    )
    if status == ms.ACTIVE:
        return covering_open
    if status == ms.FROZEN:
        return covering_frozen
    if status == ms.UPCOMING:
        return and_(~covering, future)
    if status == ms.EXPIRED:
        return and_(any_live, ~covering, ~future)
    if status == NONE:
        return ~any_live
    raise AppError(422, "bad_status", "Unknown status.")


def dues_expression():
    """Per-member dues, as a correlated SQL expression (see memberships.dues_of)."""
    owed = (
        select(
            func.coalesce(
                func.sum(
                    Membership.price - Membership.discount + Membership.admission_fee
                ),
                0,
            )
        )
        .where(Membership.member_id == Member.id, Membership.cancelled_at.is_(None))
        .scalar_subquery()
    )
    live_membership = exists().where(
        Membership.id == Payment.membership_id, Membership.cancelled_at.is_(None)
    )
    paid = (
        select(
            func.coalesce(
                func.sum(
                    case(
                        (Payment.kind == KIND_PAYMENT, Payment.amount),
                        else_=-Payment.amount,
                    )
                ),
                0,
            )
        )
        .where(
            Payment.member_id == Member.id,
            Payment.voided_at.is_(None),
            live_membership,
        )
        .scalar_subquery()
    )
    return owed - paid


def expiring_filter(today: dt.date, within_days: int):
    """Active now, and the last day of their chain falls within N days."""
    last_end = (
        select(func.max(Membership.end_date))
        .where(Membership.member_id == Member.id, Membership.cancelled_at.is_(None))
        .scalar_subquery()
    )
    return and_(
        exists().where(_covering_today(today)),
        last_end <= today + dt.timedelta(days=within_days),
    )


def search(
    ctx: StaffContext,
    *,
    q: str | None = None,
    status: str | None = None,
    branch_id: uuid.UUID | None = None,
    plan_id: uuid.UUID | None = None,
    has_dues: bool | None = None,
    expiring_within: int | None = None,
    archived: bool = False,
    today: dt.date | None = None,
) -> Select:
    today = today or today_in_nepal()
    stmt = select(Member).where(
        Member.gym_id == ctx.gym_id, Member.is_archived.is_(archived)
    )
    if ctx.branch_ids is not None:
        stmt = stmt.where(Member.home_branch_id.in_(ctx.branch_ids))
    if q:
        term = q.strip()
        digits = "".join(ch for ch in term if ch.isdigit())
        conditions = [
            Member.name.ilike(f"%{term}%"),
            Member.member_code.ilike(f"%{term}%"),
        ]
        if len(digits) >= 3:
            conditions.append(Member.phone.contains(digits[-10:]))
        stmt = stmt.where(or_(*conditions))
    if status:
        stmt = stmt.where(status_filter(status, today))
    if branch_id:
        stmt = stmt.where(Member.home_branch_id == branch_id)
    if plan_id:
        stmt = stmt.where(
            exists().where(_covering_today(today), Membership.plan_id == plan_id)
        )
    if has_dues is not None:
        dues = dues_expression()
        stmt = stmt.where(dues > 0 if has_dues else dues <= 0)
    if expiring_within is not None:
        stmt = stmt.where(expiring_filter(today, expiring_within))
    return stmt
