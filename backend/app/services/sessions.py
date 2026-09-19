"""Staff sessions: one row per signed-in device, refreshed by cookie."""

import datetime as dt
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    hash_refresh_token,
    new_refresh_token,
)
from app.core.time import utcnow
from app.models.staff import StaffSession, StaffUser
from app.services.activity import client_ip

# How long the token a session just replaced still works. Two tabs that refresh
# at the same moment both send the old cookie; without this the slower one
# signs the whole browser out.
ROTATION_GRACE = dt.timedelta(seconds=30)


@dataclass
class Issued:
    staff: StaffUser
    session: StaffSession
    access_token: str
    # None when the browser already holds the current refresh token (see
    # ROTATION_GRACE) and the cookie must be left alone.
    refresh_token: str | None


def _access_token(staff: StaffUser, session: StaffSession) -> str:
    return create_access_token(
        staff_id=staff.id, gym_id=staff.gym_id, session_id=session.id
    )


def start(db: Session, staff: StaffUser, request: Request | None) -> Issued:
    """Open a session for a staff member who has just proved who they are."""
    now = utcnow()
    raw = new_refresh_token()
    session = StaffSession(
        staff_user_id=staff.id,
        refresh_token_hash=hash_refresh_token(raw),
        user_agent=(request.headers.get("User-Agent", "")[:255] if request else None),
        ip=client_ip(request),
        expires_at=now + dt.timedelta(days=settings.refresh_token_days),
        last_used_at=now,
    )
    db.add(session)
    staff.last_login_at = now
    db.flush()
    return Issued(staff, session, _access_token(staff, session), raw)


def refresh(db: Session, raw: str | None) -> Issued | None:
    """Swap a refresh token for a new access token and a new refresh token.

    None when the token is unknown, expired or revoked, or the account can no
    longer sign in.
    """
    if not raw:
        return None
    now = utcnow()
    token_hash = hash_refresh_token(raw)
    session = db.scalars(
        select(StaffSession)
        .where(
            or_(
                StaffSession.refresh_token_hash == token_hash,
                StaffSession.previous_token_hash == token_hash,
            )
        )
        .with_for_update()
    ).first()
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        return None

    staff = db.get(StaffUser, session.staff_user_id)
    if staff is None or not staff.is_active:
        return None

    session.last_used_at = now
    if session.refresh_token_hash != token_hash:
        # The token this session replaced moments ago. Inside the grace window
        # the browser already has the new cookie from the first refresh; after
        # it, an old token turning up means it was copied, so stop honouring it.
        if session.rotated_at is None or now - session.rotated_at > ROTATION_GRACE:
            return None
        return Issued(staff, session, _access_token(staff, session), None)

    fresh = new_refresh_token()
    session.previous_token_hash = token_hash
    session.refresh_token_hash = hash_refresh_token(fresh)
    session.rotated_at = now
    db.flush()
    return Issued(staff, session, _access_token(staff, session), fresh)


def find(db: Session, raw: str | None) -> StaffSession | None:
    if not raw:
        return None
    token_hash = hash_refresh_token(raw)
    return db.scalars(
        select(StaffSession).where(
            or_(
                StaffSession.refresh_token_hash == token_hash,
                StaffSession.previous_token_hash == token_hash,
            )
        )
    ).first()


def revoke(db: Session, raw: str | None) -> StaffSession | None:
    session = find(db, raw)
    if session is not None and session.revoked_at is None:
        session.revoked_at = utcnow()
    return session


def revoke_all(db: Session, staff: StaffUser, keep=None) -> None:
    """Sign a staff member out of every device (except `keep`, a session id).

    Through the ORM, so sessions already loaded in this request see it too.
    """
    stmt = select(StaffSession).where(
        StaffSession.staff_user_id == staff.id, StaffSession.revoked_at.is_(None)
    )
    if keep is not None:
        stmt = stmt.where(StaffSession.id != keep)
    now = utcnow()
    for session in db.scalars(stmt):
        session.revoked_at = now
    db.flush()
