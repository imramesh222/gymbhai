"""Notifications for staff: what members did that someone must answer
(PLAN.md §18.6).

Web Push only, to the browsers staff turned on in My account. Each goes to
the staff who could act on it, at the branches their screens show, and only
while the sign-in that turned the browser on is live: a phone signed out, or
whose sign-in ran out, gets nothing more. Sent from the worker, like members'
push, and never an SMS instead: the red counts and the lists are still there.
"""

import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import staff_push_text as words
from app.core.calendar import format_date
from app.core.permissions import Permission, effective_permissions
from app.core.push_keys import public_key
from app.core.time import utcnow
from app.models.gym import Gym
from app.models.lead import Lead
from app.models.member import Member
from app.models.member_app import REQUEST_PENDING, FreezeRequest, PaymentRequest
from app.models.plan import Plan
from app.models.push import StaffPushSubscription
from app.models.staff import StaffBranchAccess, StaffSession, StaffUser
from app.services.push.providers import (
    PushError,
    PushGone,
    PushMessage,
    Target,
    get_provider,
)

JOB_STAFF_PUSH = "push.staff"

PAYMENT_REQUEST = "payment_request"
FREEZE_REQUEST = "freeze_request"
LEAD = "lead"
# Each kind, with the permission its screen needs: who may get it.
KINDS: dict[str, Permission] = {
    PAYMENT_REQUEST: Permission.PAYMENTS_APPROVE_APP,
    FREEZE_REQUEST: Permission.MEMBERSHIPS_FREEZE,
    LEAD: Permission.LEADS_MANAGE,
}
# Where tapping one opens.
URLS: dict[str, str] = {
    PAYMENT_REQUEST: "/staff/payment-requests",
    FREEZE_REQUEST: "/staff/freeze-requests",
    LEAD: "/staff/enquiries",
}


def available() -> bool:
    """Web Push needs our VAPID key; without one, nothing is sent."""
    return public_key() is not None


def kinds_for(permissions: Iterable[Permission]) -> list[str]:
    """The kinds someone with these permissions may get, in a fixed order."""
    held = set(permissions)
    return [kind for kind, needed in KINDS.items() if needed in held]


def _live(now: dt.datetime):
    """On, and the sign-in that turned it on still signed in."""
    return (
        StaffPushSubscription.revoked_at.is_(None),
        StaffSession.revoked_at.is_(None),
        StaffSession.expires_at > now,
        StaffUser.is_active,
    )


def live(db: Session, staff_id: uuid.UUID) -> list[StaffPushSubscription]:
    """The browsers that take this staff member's notifications now."""
    return list(
        db.scalars(
            select(StaffPushSubscription)
            .join(StaffSession, StaffSession.id == StaffPushSubscription.session_id)
            .join(StaffUser, StaffUser.id == StaffPushSubscription.staff_user_id)
            .where(StaffPushSubscription.staff_user_id == staff_id, *_live(utcnow()))
        )
    )


def _row(db: Session, staff: StaffUser, endpoint: str) -> StaffPushSubscription | None:
    return db.scalar(
        select(StaffPushSubscription).where(
            StaffPushSubscription.staff_user_id == staff.id,
            StaffPushSubscription.endpoint == endpoint,
        )
    )


def on_here(
    db: Session, staff: StaffUser, session: StaffSession, endpoint: str | None
) -> bool:
    """Whether this browser, signed in as this session, takes them."""
    if endpoint is None:
        return False
    row = _row(db, staff, endpoint)
    return row is not None and row.revoked_at is None and row.session_id == session.id


def subscribe(
    db: Session,
    staff: StaffUser,
    session: StaffSession,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str | None,
) -> StaffPushSubscription:
    """This browser takes notifications now, for this sign-in. The same browser
    again replaces its keys instead of adding a row."""
    row = _row(db, staff, endpoint)
    if row is None:
        row = StaffPushSubscription(staff_user_id=staff.id, endpoint=endpoint)
        db.add(row)
    row.session_id = session.id
    row.p256dh = p256dh
    row.auth = auth
    row.user_agent = (user_agent or "")[:300] or None
    row.revoked_at = None
    db.flush()
    return row


def resume(db: Session, staff: StaffUser, session: StaffSession, endpoint: str) -> bool:
    """Signed in again in a browser that had them on: the same person picks
    them up without being asked. Anyone else signing in there has no row for
    it, and starts with them off. Returns whether anything changed: the
    dashboard asks on every load, and most times it already belongs here."""
    row = _row(db, staff, endpoint)
    if row is None or row.revoked_at is not None or row.session_id == session.id:
        return False
    row.session_id = session.id
    return True


def unsubscribe(db: Session, staff: StaffUser, endpoint: str) -> bool:
    row = _row(db, staff, endpoint)
    if row is None or row.revoked_at is not None:
        return False
    row.revoked_at = utcnow()
    return True


# --- who gets what ---------------------------------------------------------------


def recipients(
    db: Session, gym_id: uuid.UUID, kind: str, branch_id: uuid.UUID | None
) -> list[StaffUser]:
    """Staff who'd get this now: they may see it, at that branch (None: the
    whole gym's, such as app payments), haven't turned it off, and have a
    browser that takes it. Three queries, however many staff."""
    now = utcnow()
    staff = list(
        db.scalars(
            select(StaffUser)
            .join(
                StaffPushSubscription,
                StaffPushSubscription.staff_user_id == StaffUser.id,
            )
            .join(StaffSession, StaffSession.id == StaffPushSubscription.session_id)
            .where(StaffUser.gym_id == gym_id, *_live(now))
            .distinct()
        )
    )
    if not staff:
        return []
    branches: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    if branch_id is not None:
        for staff_id, branch in db.execute(
            select(StaffBranchAccess.staff_user_id, StaffBranchAccess.branch_id).where(
                StaffBranchAccess.staff_user_id.in_([s.id for s in staff])
            )
        ):
            branches[staff_id].add(branch)
    needed = KINDS[kind]
    chosen = []
    for person in staff:
        if kind in (person.muted_notifications or []):
            continue
        if needed not in effective_permissions(
            is_owner=person.is_owner, stored=person.permissions
        ):
            continue
        # The owner, and staff with no branches ticked, work at every branch.
        theirs = branches.get(person.id)
        if branch_id is not None and not person.is_owner and theirs:
            if branch_id not in theirs:
                continue
        chosen.append(person)
    return sorted(chosen, key=lambda s: s.name)


def notify(
    db: Session,
    gym: Gym,
    kind: str,
    *,
    branch_id: uuid.UUID | None,
    text: Callable[[str], tuple[str, str]],
) -> int:
    """Queue it for everyone who'd get it, in each one's own language
    (`text(language)` gives the title and body). Returns how many."""
    if not available():
        return 0
    from app.worker import enqueue

    people = recipients(db, gym.id, kind, branch_id)
    for person in people:
        title, body = text(person.language or gym.config.language)
        enqueue(
            db,
            JOB_STAFF_PUSH,
            {
                "staff_id": str(person.id),
                "title": title,
                "body": body,
                "url": URLS[kind],
                # A newer one of the same kind replaces the last on the phone.
                "tag": kind,
            },
        )
    return len(people)


# --- what members did -------------------------------------------------------------


def payment_request(db: Session, row: PaymentRequest) -> int:
    """A member sent "I've paid" from the app: the approvers, gym-wide."""
    from app.services.receipts import rupees

    gym = db.get(Gym, row.gym_id)
    member = db.get(Member, row.member_id)
    plan = db.get(Plan, row.plan_id)
    assert gym is not None and member is not None and plan is not None
    waiting = db.scalar(
        select(func.count()).where(
            PaymentRequest.gym_id == gym.id, PaymentRequest.status == REQUEST_PENDING
        )
    )

    def text(language: str) -> tuple[str, str]:
        title = (
            words.PAYMENTS_TITLE[language].format(count=waiting)
            if waiting and waiting > 1
            else words.PAYMENT_TITLE[language]
        )
        body = words.PAYMENT_BODY[language].format(
            name=member.name, amount=rupees(row.amount), plan=plan.name
        )
        return title, body

    return notify(db, gym, PAYMENT_REQUEST, branch_id=None, text=text)


def freeze_request(db: Session, row: FreezeRequest) -> int:
    """A member asked to freeze: staff who freeze, at their home branch."""
    gym = db.get(Gym, row.gym_id)
    member = db.get(Member, row.member_id)
    assert gym is not None and member is not None
    waiting = db.scalar(
        select(func.count()).where(
            FreezeRequest.gym_id == gym.id, FreezeRequest.status == REQUEST_PENDING
        )
    )
    days = (row.to_date - row.from_date).days + 1
    date = format_date(row.from_date, gym.config.date_display)

    def text(language: str) -> tuple[str, str]:
        title = (
            words.FREEZES_TITLE[language].format(count=waiting)
            if waiting and waiting > 1
            else words.FREEZE_TITLE[language]
        )
        body = (words.FREEZE_BODY_ONE_DAY if days == 1 else words.FREEZE_BODY)[
            language
        ].format(name=member.name, days=days, date=date)
        return title, body

    return notify(db, gym, FREEZE_REQUEST, branch_id=member.home_branch_id, text=text)


def lead(db: Session, gym: Gym, row: Lead) -> int:
    """Someone asked to join from the gym's QR: staff who handle enquiries,
    at its branch."""
    plan = db.get(Plan, row.plan_id) if row.plan_id else None

    def text(language: str) -> tuple[str, str]:
        values = {"name": row.name, "phone": row.phone or "", "plan": ""}
        if plan is not None:
            values["plan"] = plan.name
            return words.LEAD_TITLE[language], words.LEAD_BODY_PLAN[language].format(
                **values
            )
        return words.LEAD_TITLE[language], words.LEAD_BODY[language].format(**values)

    return notify(db, gym, LEAD, branch_id=row.branch_id, text=text)


# --- the worker's half ------------------------------------------------------------


def handle_send(db: Session, payload: dict) -> None:
    """Every browser that takes them now. A push service that fails for now
    makes the job retry, unless one browser already took it; one that says
    the subscription is gone turns it off."""
    message = PushMessage(
        title=payload["title"],
        body=payload["body"],
        url=payload["url"],
        tag=payload.get("tag"),
    )
    delivered = False
    failed: PushError | None = None
    for row in live(db, uuid.UUID(payload["staff_id"])):
        target = Target(endpoint=row.endpoint, p256dh=row.p256dh, auth=row.auth)
        try:
            get_provider(target).send(target, message)
        except PushGone:
            row.revoked_at = utcnow()
        except PushError as exc:
            failed = exc
        else:
            row.last_ok_at = utcnow()
            delivered = True
    if failed is not None and not delivered:
        raise failed
