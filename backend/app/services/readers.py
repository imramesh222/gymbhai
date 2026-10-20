"""Fingerprint and face readers at the door (PLAN.md §18.2): one interface,
whichever brand.

GymBhai works out what each reader should hold, its members with the last
day each may come in, and the reader collects the changes when it next asks
(a ZKTeco reader itself, over ADMS; a Hikvision reader through the bridge at
the gym). Nothing is pushed from here: a reader that was offline catches up
on its next request, and a membership ending at midnight needs no job.

Each scan a reader reports becomes a check-in through the same service as a
QR scan, under the same rules, dated when the member was at the door.

Fingerprints and faces stay on the reader: GymBhai keeps only which reader
user is which member, and never stores a template a reader sends.
"""

import datetime as dt
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.time import NEPAL, today_in_nepal, utcnow
from app.models.gym import Gym
from app.models.member import Member
from app.models.member_app import (
    DEVICE_ZKTECO,
    METHOD_CARD,
    METHOD_FACE,
    METHOD_FINGERPRINT,
    METHOD_PIN,
    CheckIn,
    Device,
    ReaderUser,
)
from app.models.membership import Membership
from app.models.plan import Plan
from app.services import checkins
from app.services import members as members_service
from app.services import memberships as ms

# Kept on a reader this long after their membership ended, so a member who
# renews late still finds their fingerprint there; then taken off.
KEEP_DAYS = 90
# Worked out again at most this often while a reader keeps asking.
RECHECK = dt.timedelta(seconds=30)
# A change sent and not answered is sent again after this.
RESEND = dt.timedelta(minutes=2)
# Commands handed out per request: a reader with hundreds to take in gets
# them a batch at a time.
BATCH = 25
# What fits on a reader's screen.
NAME_LENGTH = 24


@dataclass(frozen=True)
class Want:
    """What a reader should know about one member."""

    pin: str
    name: str
    on_reader: bool
    # The last day it lets them in; None: not now (expired, frozen, not yet).
    until: dt.date | None


@dataclass(frozen=True)
class Command:
    """One change for a reader to make: put a member on it (or update them),
    or take them off."""

    id: int
    action: str  # "set" or "remove"
    pin: str
    name: str
    until: dt.date | None


def pin_of(member: Member) -> str:
    """Their number on every reader: the digits of their member code, so the
    desk can say "enrol under 48" for HFC-0048."""
    digits = re.sub(r"\D", "", member.member_code).lstrip("0")
    return digits or "0"


def wanted(db: Session, device: Device, today: dt.date | None = None) -> dict:
    """Every member this reader should hold or let go of, by member id."""
    today = today or today_in_nepal()
    cutoff = today - dt.timedelta(days=KEEP_DAYS)
    recent = exists().where(
        Membership.member_id == Member.id,
        Membership.cancelled_at.is_(None),
        Membership.end_date >= cutoff,
    )
    known = exists().where(
        ReaderUser.member_id == Member.id, ReaderUser.device_id == device.id
    )
    members = list(
        db.scalars(
            select(Member).where(Member.gym_id == device.gym_id, or_(recent, known))
        )
    )
    states = members_service.states_for(db, members, today)
    covers: dict[uuid.UUID | None, bool] = {}
    found: dict[uuid.UUID, Want] = {}
    for member in members:
        state = states[member.id]
        gone = member.is_archived or member.erased_at is not None
        keep = not gone and (
            state.status in (ms.ACTIVE, ms.FROZEN, ms.UPCOMING)
            or (state.valid_until is not None and state.valid_until >= cutoff)
        )
        until = None
        if keep and state.status == ms.ACTIVE and not state.used_up_today:
            plan_id = state.current.plan_id if state.current else None
            if plan_id not in covers:
                plan = db.get(Plan, plan_id) if plan_id else None
                covers[plan_id] = plan is None or ms.plan_covers_branch(
                    db, plan, device.branch_id
                )
            if covers[plan_id]:
                until = state.valid_until
        found[member.id] = Want(
            pin=pin_of(member),
            name=member.name[:NAME_LENGTH],
            on_reader=keep,
            until=until,
        )
    return found


def _same(row: ReaderUser, want: Want, device: Device) -> bool:
    if row.on_reader != want.on_reader or row.name != want.name:
        return False
    # A ZKTeco reader takes no end dates yet: they change nothing on it
    # (§18.2, to confirm on a real reader).
    return device.kind == DEVICE_ZKTECO or row.until == want.until


def _next_id(device: Device) -> int:
    device.command_seq += 1
    return device.command_seq


def reconcile(db: Session, device: Device, now: dt.datetime | None = None) -> int:
    """Make the reader's rows say what it should hold; a changed row becomes a
    command to send. Returns how many changed."""
    now = now or utcnow()
    rows = {
        row.member_id: row
        for row in db.scalars(
            select(ReaderUser).where(ReaderUser.device_id == device.id)
        )
    }
    changed = 0
    for member_id, want in wanted(db, device).items():
        row = rows.get(member_id)
        if row is None:
            if not want.on_reader:
                continue
            row = ReaderUser(
                gym_id=device.gym_id,
                device_id=device.id,
                member_id=member_id,
                pin=want.pin,
            )
            db.add(row)
        elif _same(row, want, device):
            continue
        row.name = want.name
        row.on_reader = want.on_reader
        row.until = want.until
        row.command_id = _next_id(device)
        row.sent_at = None
        row.done_at = None
        row.error = None
        changed += 1
    device.synced_at = now
    db.flush()
    return changed


def commands(db: Session, device: Device, limit: int = BATCH) -> list[Command]:
    """What the reader should do now: changes not yet answered, oldest first,
    each sent again if no answer came."""
    now = utcnow()
    if device.synced_at is None or now - device.synced_at >= RECHECK:
        reconcile(db, device, now)
    rows = list(
        db.scalars(
            select(ReaderUser)
            .where(
                ReaderUser.device_id == device.id,
                ReaderUser.done_at.is_(None),
                or_(ReaderUser.sent_at.is_(None), ReaderUser.sent_at < now - RESEND),
            )
            .order_by(ReaderUser.command_id)
            .limit(limit)
        )
    )
    for row in rows:
        row.sent_at = now
    return [
        Command(
            id=row.command_id or 0,
            action="set" if row.on_reader else "remove",
            pin=row.pin,
            name=row.name,
            until=row.until,
        )
        for row in rows
    ]


def answered(
    db: Session, device: Device, command_id: int, ok: bool, error: str | None = None
) -> bool:
    """The reader's answer to a command. False when it answers one we don't
    know, or an older one since replaced."""
    row = db.scalar(
        select(ReaderUser).where(
            ReaderUser.device_id == device.id, ReaderUser.command_id == command_id
        )
    )
    if row is None:
        return False
    if ok:
        row.done_at = utcnow()
        row.error = None
    else:
        # Tried again after RESEND; the reader's words kept for the desk.
        row.error = (error or "failed")[:500]
    return True


def counts(
    db: Session, device_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int]]:
    """For each reader: members on it, and changes waiting to reach it."""
    if not device_ids:
        return {}
    rows = db.execute(
        select(
            ReaderUser.device_id,
            func.count().filter(ReaderUser.on_reader),
            func.count().filter(ReaderUser.done_at.is_(None)),
        )
        .where(ReaderUser.device_id.in_(device_ids))
        .group_by(ReaderUser.device_id)
    )
    return {device_id: (on, waiting) for device_id, on, waiting in rows}


# --- scans ---------------------------------------------------------------------------

# How a ZKTeco reader says the member proved who they were (its VerifyMode).
ZKTECO_VERIFY = {0: METHOD_PIN, 1: METHOD_FINGERPRINT, 2: METHOD_CARD, 15: METHOD_FACE}
HOW = (METHOD_FINGERPRINT, METHOD_FACE, METHOD_CARD, METHOD_PIN)


def member_for_pin(db: Session, device: Device, pin: str) -> Member | None:
    """The member a reader user is, as GymBhai put them on this reader. A
    user someone enrolled on the reader by hand (staff, or members from before
    GymBhai) isn't anyone here: guessing by number could put one person's
    visits on another (§18.2)."""
    row = db.scalar(
        select(ReaderUser).where(
            ReaderUser.device_id == device.id, ReaderUser.pin == pin
        )
    )
    return db.get(Member, row.member_id) if row is not None else None


# A reader's clock a little ahead is forgiven; further, the scan is not believed.
CLOCK_SLACK = dt.timedelta(minutes=10)


def scan(
    db: Session, device: Device, pin: str, at: dt.datetime, how: str
) -> CheckIn | None:
    """A scan the reader reports. None for a reader user who isn't a member
    (staff enrolled on it, say), a scan already recorded (a reader sends
    again what it isn't sure arrived), or one that can't be a visit here."""
    # Scans from before the gym added the reader (a reader sends all it has
    # when it first connects), or from a clock set wrong, aren't visits here.
    if at < device.created_at or at > utcnow() + CLOCK_SLACK:
        return None
    member = member_for_pin(db, device, pin.strip())
    if member is None:
        return None
    if db.scalar(
        select(CheckIn.id).where(
            CheckIn.device_id == device.id,
            CheckIn.member_id == member.id,
            CheckIn.at == at,
        )
    ):
        return None
    gym = db.get(Gym, device.gym_id)
    assert gym is not None
    outcome = checkins.check_in(
        db,
        gym=gym,
        member=member,
        branch_id=device.branch_id,
        method=how if how in HOW else METHOD_FINGERPRINT,
        device_id=device.id,
        at=at,
    )
    return outcome.check_in


def local_time(text: str) -> dt.datetime:
    """A reader's "2026-10-20 06:15:22", in the gym's time: readers keep
    Nepal time on their own clock."""
    return dt.datetime.strptime(text.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=NEPAL)
