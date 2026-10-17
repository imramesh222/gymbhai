"""Checking members in at the door (PLAN.md §4.3).

One service for every way in — kiosk, staff phone, USB scanner, manual — so
fingerprint and face readers can be added later as just another source.

The rules, in order:
* Scanned again within the re-scan window  -> duplicate ("already checked in")
* Frozen today                             -> denied_frozen
* No membership covering today             -> warned within the grace days after
                                              expiry, otherwise denied_expired
* A visit pack with every visit used       -> denied_visits_used (§16.4, 9.3)
* Plan not sold at this branch             -> denied_branch
* An off-peak plan, outside its hours      -> denied_hours (9.4)
* Owes money                               -> the gym's dues rule: allow, warn
                                              (the default) or refuse (denied_dues)
* Otherwise                                -> allowed

Every scan is recorded, allowed or not: denied scans are how owners see who
is trying to train unpaid. Staff with "let someone in despite an expired
membership" can override a denial; that is recorded too.
"""

import datetime as dt
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
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
    LET_IN,
    METHOD_APP_QR,
    METHOD_CARD_QR,
    OVERRIDE,
    WARNED,
    CheckIn,
)
from app.models.plan import Plan
from app.services import live
from app.services import members as members_service
from app.services import memberships as ms


@dataclass
class Outcome:
    check_in: CheckIn
    member: Member
    state: members_service.MemberState
    # Why a warning or a denial: expired_grace, dues, frozen, expired, branch.
    reason: str | None = None

    @property
    def let_in(self) -> bool:
        return self.check_in.result in LET_IN or self.check_in.result == DUPLICATE


def find_by_code(
    db: Session, gym_id: uuid.UUID, code: str
) -> tuple[Member, str] | None:
    """The member a scanned code belongs to, and how it was presented."""
    scanned = qr.parse(code)
    if scanned is None:
        return None
    if scanned.kind == "card":
        member = db.scalars(
            select(Member).where(
                Member.gym_id == gym_id, Member.card_token == scanned.card_token
            )
        ).first()
        return (member, METHOD_CARD_QR) if member else None
    member = db.get(Member, scanned.member_id)
    if member is None or member.gym_id != gym_id:
        return None
    if not qr.verify_app_code(
        scanned, member.qr_secret, member.qr_version, time.time()
    ):
        return None
    return member, METHOD_APP_QR


def within_hours(hours: list[dict] | None, at: dt.datetime) -> bool:
    """An off-peak plan's windows, in Nepal time; none means any time."""
    if not hours:
        return True
    local = at.astimezone(NEPAL)
    now = local.strftime("%H:%M")
    return any(
        local.weekday() in w["days"] and w["from"] <= now < w["to"] for w in hours
    )


def _decide(
    db: Session, gym: Gym, member: Member, branch_id: uuid.UUID, now: dt.datetime
) -> tuple[str, str | None, members_service.MemberState]:
    config = gym.config
    today = today_in_nepal(now)
    state = members_service.state(db, member)

    if state.status == ms.FROZEN:
        return DENIED_FROZEN, "frozen", state
    if state.used_up_today and not member.is_archived:
        return DENIED_VISITS_USED, "visits_used", state
    if state.status != ms.ACTIVE or member.is_archived:
        if (
            state.status == ms.EXPIRED
            and state.valid_until is not None
            and (today - state.valid_until).days <= config.grace_days
        ):
            return WARNED, "expired_grace", state
        return DENIED_EXPIRED, "expired", state

    current = state.current
    assert current is not None
    plan = db.get(Plan, current.plan_id) if current.plan_id else None
    if plan is not None and not ms.plan_covers_branch(db, plan, branch_id):
        return DENIED_BRANCH, "branch", state
    if not within_hours(current.access_hours, now):
        return DENIED_HOURS, "hours", state

    if state.dues > 0:
        if config.dues_rule == "refuse":
            return DENIED_DUES, "dues", state
        if config.dues_rule == "warn":
            return WARNED, "dues", state
    return ALLOWED, None, state


def check_in(
    db: Session,
    *,
    gym: Gym,
    member: Member,
    branch_id: uuid.UUID,
    method: str,
    device_id: uuid.UUID | None = None,
    staff_id: uuid.UUID | None = None,
    override: bool = False,
    note: str | None = None,
) -> Outcome:
    # A camera often reads the same QR twice in a second: locked, the second
    # scan sees the first and is marked a duplicate instead of a second visit.
    ms.lock_member(db, member)
    now = utcnow()
    result, reason, state = _decide(db, gym, member, branch_id, now)

    if result in LET_IN and gym.config.rescan_minutes:
        recent = db.scalar(
            select(CheckIn.id).where(
                CheckIn.member_id == member.id,
                CheckIn.result.in_(LET_IN),
                CheckIn.at >= now - dt.timedelta(minutes=gym.config.rescan_minutes),
            )
        )
        if recent:
            result = DUPLICATE
    if override and result not in LET_IN and result != DUPLICATE:
        result = OVERRIDE

    row = CheckIn(
        gym_id=gym.id,
        branch_id=branch_id,
        member_id=member.id,
        membership_id=state.current.id if state.current else None,
        at=now,
        method=method,
        result=result,
        device_id=device_id,
        staff_user_id=staff_id,
        note=note,
    )
    db.add(row)
    db.flush()
    live.publish(
        db, gym_id=gym.id, kind=live.CHECK_IN, member_id=member.id, branch_id=branch_id
    )
    return Outcome(check_in=row, member=member, state=state, reason=reason)


# --- how busy now (PLAN.md §16.3, 8.5) ---

BUSY_WINDOW = dt.timedelta(hours=2)
BUSY_WEEKS = 4


def busyness(
    db: Session, gym_id: uuid.UUID, branch_id: uuid.UUID, now: dt.datetime | None = None
) -> str | None:
    """ "quiet", "normal" or "busy": visits in the last two hours at the branch,
    against the same two hours on the same weekday over the last four weeks.
    None until there are a few weeks to compare with."""
    now = now or utcnow()
    windows = [
        (now - dt.timedelta(weeks=k) - BUSY_WINDOW, now - dt.timedelta(weeks=k))
        for k in range(BUSY_WEEKS + 1)
    ]
    counts = db.execute(
        select(
            *(
                func.count().filter(CheckIn.at > start, CheckIn.at <= end)
                for start, end in windows
            )
        ).where(
            CheckIn.gym_id == gym_id,
            CheckIn.branch_id == branch_id,
            CheckIn.result.in_(LET_IN),
            CheckIn.at > windows[-1][0],
        )
    ).one()
    current, past = counts[0], counts[1:]
    typical = sum(past) / BUSY_WEEKS
    if typical < 2:
        return None  # too new, or too little at this hour, to say
    if current < typical * 0.6:
        return "quiet"
    if current > typical * 1.3:
        return "busy"
    return "normal"
