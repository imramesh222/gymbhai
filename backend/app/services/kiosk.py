"""The kiosk with no internet (PLAN.md §19.2).

While online, a kiosk keeps a roster of the members who could come to its
branch: for each, one letter a day for the next DAYS days, saying what the
door would decide that day before the hour, money owed and the re-scan window
are looked at. The letters come from the same state the door uses (§4.3), so
the kiosk's shared code (shared/src/door/offline.ts) only applies them.

Offline, the kiosk decides by itself and keeps each scan. Once it's back, the
scans are recorded here as check-ins with what it decided at the door: that
is what happened, so it is never decided again.
"""

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core import qr
from app.core.time import NEPAL, today_in_nepal, utcnow
from app.models.gym import Gym
from app.models.member import Member
from app.models.member_app import (
    ALLOWED,
    DENIED_BRANCH,
    DENIED_DUES,
    DENIED_EXPIRED,
    DENIED_FROZEN,
    DENIED_HOURS,
    DENIED_VISITS_USED,
    DUPLICATE,
    METHOD_APP_QR,
    METHOD_CARD_QR,
    WARNED,
    CheckIn,
    Device,
)
from app.models.membership import Membership
from app.models.plan import Plan
from app.services import live, storage
from app.services import members as members_service
from app.services import memberships as ms

DAYS = 14
# Members whose last membership ended this long ago are left off: offline,
# the kiosk sends them to the desk, as it would anyone it doesn't know.
KEEP_DAYS = 90

# One letter a day.
LET_IN_DAY = "a"
GRACE_DAY = "g"  # expired, within the gym's grace days: let in with a warning
FROZEN_DAY = "f"
EXPIRED_DAY = "x"  # also: not started, or archived
BRANCH_DAY = "b"  # their plan isn't sold at this branch
USED_DAY = "v"  # a visit pack with every visit used

# What a kiosk may say it decided.
OFFLINE_RESULTS = frozenset(
    {
        ALLOWED,
        WARNED,
        DUPLICATE,
        DENIED_EXPIRED,
        DENIED_FROZEN,
        DENIED_BRANCH,
        DENIED_DUES,
        DENIED_VISITS_USED,
        DENIED_HOURS,
    }
)
CLOCK_SLACK = dt.timedelta(minutes=10)


def day_letter(
    state: members_service.MemberState,
    day: dt.date,
    *,
    archived: bool,
    grace_days: int,
    covers: bool,
) -> str:
    """The door's rules (app/services/checkins.py `_decide`) for one day,
    before the hour and money owed."""
    if state.status == ms.FROZEN:
        return FROZEN_DAY
    if state.used_up_today and not archived:
        return USED_DAY
    if state.status != ms.ACTIVE or archived:
        if (
            state.status == ms.EXPIRED
            and state.valid_until is not None
            and (day - state.valid_until).days <= grace_days
            and not archived
        ):
            return GRACE_DAY
        return EXPIRED_DAY
    return LET_IN_DAY if covers else BRANCH_DAY


@dataclass
class RosterEntry:
    id: uuid.UUID
    name: str
    code: str
    photo: str | None
    photo_url: str | None
    card: str
    key: str
    days: str
    hours: list[dict] | None
    visits_left: int | None
    owes: bool
    plan_name: str | None
    valid_until: dt.date | None


def card_hash(card_token: str) -> str:
    """The kiosk keeps the hash of a card's token, not the token."""
    return hashlib.sha256(card_token.encode()).hexdigest()


def roster(
    db: Session, device: Device, today: dt.date | None = None
) -> list[RosterEntry]:
    """Everyone who could come to the device's branch, in a fixed number of
    queries however many members there are."""
    today = today or today_in_nepal()
    gym = db.get(Gym, device.gym_id)
    assert gym is not None
    grace = gym.config.grace_days
    recent = exists().where(
        Membership.member_id == Member.id,
        Membership.cancelled_at.is_(None),
        Membership.end_date >= today - dt.timedelta(days=KEEP_DAYS),
    )
    members = list(
        db.scalars(
            select(Member)
            .where(Member.gym_id == device.gym_id, Member.erased_at.is_(None), recent)
            .order_by(Member.member_code)
        )
    )
    inputs = members_service.state_inputs(db, members)
    plan_ids = {
        m.plan_id for rows in inputs.by_member.values() for m in rows if m.plan_id
    }
    plans = (
        {p.id: p for p in db.scalars(select(Plan).where(Plan.id.in_(plan_ids)))}
        if plan_ids
        else {}
    )
    covers: dict[uuid.UUID | None, bool] = {}

    def covered(plan_id: uuid.UUID | None) -> bool:
        if plan_id not in covers:
            plan = plans.get(plan_id) if plan_id else None
            covers[plan_id] = plan is None or ms.plan_covers_branch(
                db, plan, device.branch_id
            )
        return covers[plan_id]

    entries = []
    for member in members:
        now_state = inputs.state(member.id, today)
        letters = []
        hours = None
        for offset in range(DAYS):
            day = today + dt.timedelta(days=offset)
            state = now_state if offset == 0 else inputs.state(member.id, day)
            current = state.current
            letter = day_letter(
                state,
                day,
                archived=member.is_archived,
                grace_days=grace,
                covers=covered(current.plan_id if current else None),
            )
            if letter == LET_IN_DAY and hours is None and current is not None:
                hours = current.access_hours or []
            letters.append(letter)
        current = now_state.current
        entries.append(
            RosterEntry(
                id=member.id,
                name=member.name,
                code=member.member_code,
                photo=hashlib.sha256(member.photo_key.encode()).hexdigest()[:16]
                if member.photo_key
                else None,
                photo_url=storage.signed_url(member.photo_key),
                card=card_hash(member.card_token),
                key=qr.public_key(member.qr_secret, member.qr_version),
                days="".join(letters),
                hours=hours or None,
                visits_left=now_state.visits_left,
                owes=now_state.dues + now_state.group_dues > 0,
                plan_name=current.plan_name if current else None,
                valid_until=now_state.valid_until,
            )
        )
    return entries


@dataclass
class OfflineScan:
    client_id: str
    member_id: uuid.UUID
    method: str
    at: dt.datetime
    result: str


def record(db: Session, device: Device, scans: list[OfflineScan]) -> int:
    """The kiosk's offline scans, as check-ins with what it decided. A scan
    sent twice, for a member of another gym, or at an impossible time is
    skipped. Returns how many were recorded."""
    gym = db.get(Gym, device.gym_id)
    assert gym is not None
    now = utcnow()
    oldest = now - dt.timedelta(days=gym.config.kiosk_offline_days + 1)
    usable = [
        s
        for s in scans
        if s.result in OFFLINE_RESULTS
        and s.method in (METHOD_APP_QR, METHOD_CARD_QR)
        and oldest <= s.at <= now + CLOCK_SLACK
    ]
    ids = {s.member_id for s in usable}
    members = (
        {
            m.id: m
            for m in db.scalars(
                select(Member).where(Member.id.in_(ids), Member.gym_id == device.gym_id)
            )
        }
        if ids
        else {}
    )
    inputs = members_service.state_inputs(db, list(members.values()))
    recorded = 0
    for scan in usable:
        member = members.get(scan.member_id)
        if member is None:
            continue
        # The membership it counts against, for a visit pack: that day's.
        state = inputs.state(member.id, scan.at.astimezone(NEPAL).date())
        inserted = db.execute(
            insert(CheckIn)
            .values(
                id=uuid.uuid4(),
                gym_id=device.gym_id,
                branch_id=device.branch_id,
                member_id=member.id,
                membership_id=state.current.id if state.current else None,
                at=scan.at,
                method=scan.method,
                result=scan.result,
                device_id=device.id,
                offline=True,
                client_id=scan.client_id,
            )
            .on_conflict_do_nothing(
                index_elements=["device_id", "client_id"],
                index_where=CheckIn.client_id.is_not(None),
            )
            .returning(CheckIn.id)
        ).first()
        recorded += inserted is not None
    if recorded:
        live.publish(
            db, gym_id=device.gym_id, kind=live.CHECK_IN, branch_id=device.branch_id
        )
    return recorded
