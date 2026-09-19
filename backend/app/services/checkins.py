"""Checking members in at the door (PLAN.md §4.3).

One service for every way in — kiosk, staff phone, USB scanner, manual — so
fingerprint and face readers can be added later as just another source.

The rules, in order:
* Scanned again within the re-scan window  -> duplicate ("already checked in")
* Frozen today                             -> denied_frozen
* No membership covering today             -> warned within the grace days after
                                              expiry, otherwise denied_expired
* Plan not sold at this branch             -> denied_branch
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

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import qr
from app.core.time import today_in_nepal, utcnow
from app.models.gym import Gym
from app.models.member import Member
from app.models.member_app import (
    ALLOWED,
    DENIED_BRANCH,
    DENIED_DUES,
    DENIED_EXPIRED,
    DENIED_FROZEN,
    DUPLICATE,
    LET_IN,
    METHOD_APP_QR,
    METHOD_CARD_QR,
    OVERRIDE,
    WARNED,
    CheckIn,
)
from app.models.plan import Plan
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


def _decide(
    db: Session, gym: Gym, member: Member, branch_id: uuid.UUID, today: dt.date
) -> tuple[str, str | None, members_service.MemberState]:
    config = gym.config
    state = members_service.state(db, member)

    if state.status == ms.FROZEN:
        return DENIED_FROZEN, "frozen", state
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
    now = utcnow()
    today = today_in_nepal(now)
    result, reason, state = _decide(db, gym, member, branch_id, today)

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
    return Outcome(check_in=row, member=member, state=state, reason=reason)
