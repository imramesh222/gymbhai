"""Notifications for staff, on their own devices (PLAN.md §18.6).

Every route here is the caller's own, like their signed-in devices: a browser
is turned on for the sign-in that asked, and nobody can turn on or off
another person's.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import current_session, current_staff
from app.core.errors import AppError
from app.core.permissions import effective_permissions
from app.core.push_keys import public_key
from app.db.session import get_db
from app.models.staff import StaffSession, StaffUser
from app.schemas.auth import (
    NotificationsIn,
    StaffPushEndpoint,
    StaffPushStatus,
)
from app.schemas.member_app import PushSubscriptionIn
from app.services import activity
from app.services.push import staff as staff_push

router = APIRouter(prefix="/auth", tags=["auth"])


def _status(
    db: Session, staff: StaffUser, session: StaffSession, endpoint: str | None
) -> StaffPushStatus:
    kinds = (
        staff_push.kinds_for(
            effective_permissions(is_owner=staff.is_owner, stored=staff.permissions)
        )
        if staff.gym_id is not None
        else []
    )
    return StaffPushStatus(
        public_key=public_key(),
        on_here=staff_push.on_here(db, staff, session, endpoint),
        kinds=kinds,  # type: ignore[arg-type]
        muted=[k for k in staff.muted_notifications or [] if k in kinds],
    )


@router.get("/push", response_model=StaffPushStatus)
def my_push(
    endpoint: Annotated[str | None, Query(max_length=2000)] = None,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(current_staff),
    session: StaffSession = Depends(current_session),
) -> StaffPushStatus:
    """Whether this browser takes them, and which kinds."""
    return _status(db, staff, session, endpoint)


@router.post("/push", response_model=StaffPushStatus)
def turn_push_on(
    payload: PushSubscriptionIn,
    request: Request,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(current_staff),
    session: StaffSession = Depends(current_session),
) -> StaffPushStatus:
    """This browser takes notifications now, while this sign-in lasts. Asking
    twice (a double tap, a retry) changes nothing more."""
    if not staff_push.available():
        raise AppError(409, "push_unavailable", "Notifications aren't set up yet.")
    row = staff_push.subscribe(
        db,
        staff,
        session,
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
        user_agent=request.headers.get("user-agent"),
    )
    activity.staff_action(
        db,
        staff,
        "staff.push_on",
        entity="staff_push_subscription",
        entity_id=row.id,
        request=request,
    )
    db.commit()
    return _status(db, staff, session, payload.endpoint)


@router.post("/push/resume", response_model=StaffPushStatus)
def resume_push(
    payload: StaffPushEndpoint,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(current_staff),
    session: StaffSession = Depends(current_session),
) -> StaffPushStatus:
    """Signed in again in a browser that had them on: the same person picks
    them up; anyone else isn't (they never turned it on)."""
    if staff_push.resume(db, staff, session, payload.endpoint):
        db.commit()
    return _status(db, staff, session, payload.endpoint)


@router.post("/push/off", response_model=StaffPushStatus)
def turn_push_off(
    payload: StaffPushEndpoint,
    request: Request,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(current_staff),
    session: StaffSession = Depends(current_session),
) -> StaffPushStatus:
    if staff_push.unsubscribe(db, staff, payload.endpoint):
        activity.staff_action(
            db,
            staff,
            "staff.push_off",
            entity="staff",
            entity_id=staff.id,
            request=request,
        )
        db.commit()
    return _status(db, staff, session, payload.endpoint)


@router.put("/me/notifications", response_model=StaffPushStatus)
def choose_notifications(
    payload: NotificationsIn,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(current_staff),
    session: StaffSession = Depends(current_session),
) -> StaffPushStatus:
    """The ticks, for every browser of theirs: kept as what's turned off."""
    staff.muted_notifications = sorted(set(payload.muted))
    db.commit()
    return _status(db, staff, session, payload.endpoint)
