"""Turning rows plus their computed state into API responses."""

import uuid
from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import today_in_nepal
from app.models.member import Member
from app.models.member_app import READERS, Device, MemberSession
from app.models.membership import Membership, MembershipFreeze, MembershipGroup
from app.models.payment import Payment
from app.models.staff import StaffUser
from app.schemas.members import (
    CurrentMembership,
    FreezeRead,
    GroupPerson,
    MemberDetail,
    MemberRead,
    MembershipGroupRead,
    MembershipRead,
)
from app.schemas.money import PaymentRead
from app.services import members as members_service
from app.services import memberships as ms
from app.services import readers, storage
from app.services.members import MemberState


def staff_names(db: Session, ids: Sequence[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = db.execute(
        select(StaffUser.id, StaffUser.name).where(StaffUser.id.in_(wanted))
    )
    return {row.id: row.name for row in rows}


def payment_read(payment: Payment, names: dict[uuid.UUID, str]) -> PaymentRead:
    read = PaymentRead.model_validate(payment)
    read.received_by_name = (
        names.get(payment.received_by) if payment.received_by else None
    )
    return read


def payments_read(db: Session, payments: Sequence[Payment]) -> list[PaymentRead]:
    names = staff_names(db, [p.received_by for p in payments])
    return [payment_read(p, names) for p in payments]


def groups_read(
    db: Session, group_ids: Sequence[uuid.UUID | None]
) -> dict[uuid.UUID, MembershipGroupRead]:
    """Family and couple plans (§19.1): who is on each, the payer first.
    Two queries for any number of plans, none without one."""
    wanted = {g for g in group_ids if g is not None}
    if not wanted:
        return {}
    groups = {
        g.id: g
        for g in db.scalars(
            select(MembershipGroup).where(MembershipGroup.id.in_(wanted))
        )
    }
    rows = db.execute(
        select(Membership, Member.name, Member.member_code)
        .join(Member, Member.id == Membership.member_id)
        .where(Membership.group_id.in_(wanted))
        .order_by(Membership.created_at, Membership.id)
    ).all()
    people: dict[uuid.UUID, list[GroupPerson]] = defaultdict(list)
    for membership, name, code in rows:
        people[membership.group_id].append(
            GroupPerson(
                member_id=membership.member_id,
                name=name,
                member_code=code,
                membership_id=membership.id,
                cancelled=membership.cancelled_at is not None,
            )
        )
    found = {}
    for group_id, group in groups.items():
        # The payer first, then by name: everyone sold together shares a
        # timestamp, so that order says nothing.
        everyone = sorted(
            people[group_id],
            key=lambda p: (p.member_id != group.payer_member_id, p.name),
        )
        payer = next(
            (p for p in everyone if p.member_id == group.payer_member_id), None
        )
        found[group_id] = MembershipGroupRead(
            id=group.id,
            seats=group.seats,
            payer_member_id=group.payer_member_id,
            payer_name=payer.name if payer else "",
            people=everyone,
        )
    return found


def membership_read(
    membership: Membership,
    freezes: Sequence[MembershipFreeze],
    payments: Sequence[Payment],
    visits_used: int | None = None,
    groups: dict[uuid.UUID, MembershipGroupRead] | None = None,
) -> MembershipRead:
    read = MembershipRead.model_validate(membership)
    today = today_in_nepal()
    read.status = ms.status_of(membership, freezes, today)
    if membership.visit_limit is not None:
        read.visits_used = visits_used or 0
        # Every visit used: over, whatever the dates say (§16.4, 9.3).
        if read.visits_used >= membership.visit_limit and read.status in (
            ms.ACTIVE,
            ms.FROZEN,
        ):
            read.status = ms.EXPIRED
    read.days_left = (
        ms.days_left(membership, today) if read.status in (ms.ACTIVE, ms.FROZEN) else 0
    )
    read.total = ms.amount_due(membership)
    read.paid = ms.net_paid(payments)
    read.dues = ms.dues_of(membership, payments)
    read.freezes = [FreezeRead.model_validate(f) for f in freezes]
    if membership.group_id is not None and groups:
        read.group = groups.get(membership.group_id)
    return read


def membership_read_one(db: Session, membership: Membership) -> MembershipRead:
    return membership_read(
        membership,
        ms.freezes_for(db, [membership.id]),
        ms.payments_for(db, [membership.id]),
        ms.visits_used(db, [membership]).get(membership.id),
        groups_read(db, [membership.group_id]),
    )


def member_read(member: Member, state: MemberState) -> MemberRead:
    read = MemberRead.model_validate(member)
    read.photo_url = storage.signed_url(member.photo_key)
    read.status = state.status
    read.valid_until = state.valid_until
    read.days_left = state.days_left
    read.dues = state.dues
    read.group_dues = state.group_dues
    if state.current is not None:
        read.current = CurrentMembership(
            id=state.current.id,
            plan_name=state.current.plan_name,
            start_date=state.current.start_date,
            end_date=state.current.end_date,
            visit_limit=state.visit_limit,
            visits_left=state.visits_left,
            access_hours=state.current.access_hours,
        )
    return read


def member_detail(db: Session, member: Member) -> MemberDetail:
    memberships = ms.memberships_of(db, member)
    ids = [m.id for m in memberships]
    freezes: dict[uuid.UUID, list[MembershipFreeze]] = defaultdict(list)
    for f in ms.freezes_for(db, ids):
        freezes[f.membership_id].append(f)
    membership_payments: dict[uuid.UUID, list[Payment]] = defaultdict(list)
    for p in ms.payments_for(db, ids):
        membership_payments[p.membership_id].append(p)  # type: ignore[index]
    # From the rows already loaded, not a second round of the same queries.
    visits = ms.visits_used(db, memberships)
    state = members_service.state_of(
        memberships, freezes, membership_payments, visits=visits
    )
    state.group_dues = ms.group_dues_for(db, memberships).get(member.id, 0)
    groups = groups_read(db, [m.group_id for m in memberships])

    all_payments = list(
        db.scalars(
            select(Payment)
            .where(Payment.member_id == member.id, Payment.gym_id == member.gym_id)
            .order_by(Payment.paid_at.desc())
        )
    )
    base = member_read(member, state)
    referrer = db.get(Member, member.referred_by_id) if member.referred_by_id else None
    return MemberDetail(
        **base.model_dump(),
        referred_by_name=referrer.name if referrer else None,
        memberships=[
            membership_read(
                m, freezes[m.id], membership_payments[m.id], visits.get(m.id), groups
            )
            for m in memberships
        ],
        payments=payments_read(db, all_payments),
        renewal_starts_on=ms.renewal_start(db, member),
        first_membership=ms.is_first_membership(db, member),
        app_signed_in_at=db.scalar(
            select(func.max(MemberSession.created_at)).where(
                MemberSession.member_id == member.id
            )
        ),
        reader_pin=readers.pin_of(member) if _has_readers(db, member.gym_id) else None,
    )


def _has_readers(db: Session, gym_id: uuid.UUID) -> bool:
    return bool(
        db.scalar(
            select(Device.id).where(
                Device.gym_id == gym_id,
                Device.kind.in_(READERS),
                Device.revoked_at.is_(None),
            )
        )
    )
