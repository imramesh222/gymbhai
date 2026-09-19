"""Member sign-in by a code sent to their phone or email (PLAN.md §5.5, §11).

* Only people the gym has added can sign in; there is no self sign-up.
* A number the gym hasn't added gets the same answer however it got there —
  never a hint that it belongs to another gym, or that its access is off.
* One phone, several members (a parent and children): after the code is
  right, the member picks who they are.
* Codes: 6 digits, 5 minutes, 5 wrong tries; at most 3 per phone or email
  per 15 minutes and a limit per address, because each one costs us an SMS.
  They are never charged to the gym and never blocked by its credit (§5.7).
"""

import datetime as dt
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.phone import normalize_phone
from app.core.security import (
    create_member_token,
    hash_refresh_token,
    new_refresh_token,
)
from app.core.time import utcnow
from app.models.gym import Gym
from app.models.member import Member
from app.models.member_app import MemberSession, OtpCode
from app.models.messaging import SMS_OTP, SmsMessage
from app.services import email
from app.services.activity import client_ip
from app.services.sms import service as sms

ROTATION_GRACE = dt.timedelta(seconds=30)
REDACTED = "Sign-in code (hidden)"


def not_registered(gym: Gym) -> AppError:
    return AppError(
        404,
        "not_registered",
        f"This number isn't registered with {gym.name}. Please ask at the desk.",
    )


@dataclass(frozen=True)
class Destination:
    channel: str  # "sms" or "email"
    value: str


def destination(phone: str | None, email_address: str | None) -> Destination:
    if phone:
        try:
            return Destination("sms", normalize_phone(phone))
        except ValueError as exc:
            raise AppError(422, "bad_phone", str(exc)) from exc
    if email_address and "@" in email_address:
        return Destination("email", email_address.strip().lower())
    raise AppError(422, "needs_destination", "Enter your mobile number or email.")


def members_at(db: Session, gym: Gym, where: Destination) -> list[Member]:
    column = Member.phone if where.channel == "sms" else func.lower(Member.email)
    return list(
        db.scalars(
            select(Member)
            .where(
                Member.gym_id == gym.id,
                column == where.value,
                Member.app_access.is_(True),
                Member.is_archived.is_(False),
            )
            .order_by(Member.name)
        )
    )


def _hash(gym_id: uuid.UUID, where: Destination, code: str) -> str:
    message = f"{gym_id}:{where.channel}:{where.value}:{code}".encode()
    return hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()


def _rate_limited(db: Session, where: Destination, ip: str | None) -> bool:
    since = utcnow() - dt.timedelta(minutes=settings.otp_window_minutes)
    per_destination = db.scalar(
        select(func.count())
        .select_from(OtpCode)
        .where(OtpCode.destination == where.value, OtpCode.created_at >= since)
    )
    if per_destination >= settings.otp_per_destination:
        return True
    if ip:
        per_ip = db.scalar(
            select(func.count())
            .select_from(OtpCode)
            .where(OtpCode.ip == ip, OtpCode.created_at >= since)
        )
        if per_ip >= settings.otp_per_ip:
            return True
    return False


def request_code(
    db: Session, gym: Gym, where: Destination, request: Request | None = None
) -> None:
    ip = client_ip(request)
    if _rate_limited(db, where, ip):
        raise AppError(
            429, "too_many_codes", "Too many codes asked for. Wait a few minutes."
        )
    known = bool(members_at(db, gym, where))
    code = settings.otp_test_code or f"{secrets.randbelow(1_000_000):06d}"
    # Recorded even for an unknown number, so the limits also count guesses:
    # otherwise anyone could test numbers freely to learn who trains here.
    db.add(
        OtpCode(
            gym_id=gym.id,
            channel=where.channel,
            destination=where.value,
            code_hash=_hash(gym.id, where, code),
            expires_at=utcnow() + dt.timedelta(minutes=settings.otp_minutes),
            ip=ip,
        )
    )
    if not known:
        db.commit()
        raise not_registered(gym)
    text = (
        f"{code} is your {gym.name} sign-in code. "
        f"It expires in {settings.otp_minutes} minutes."
    )
    if where.channel == "sms":
        message = SmsMessage(
            gym_id=gym.id, to=where.value, body=text, kind=SMS_OTP, segments=1
        )
        db.add(message)
        db.flush()
        # Sent now, not queued behind reminders (§9). A gateway failure is
        # reported, and the code row stays so the rate limit still counts it.
        sent = sms.send_now(db, message)
        # The SMS log is readable by staff: a code left in it would let them
        # sign in as the member.
        message.body = REDACTED
        if not sent:
            db.commit()
            raise AppError(503, "sms_failed", "We couldn't send the SMS. Try again.")
    else:
        try:
            email.send(where.value, f"Your {gym.name} sign-in code", text)
        except email.EmailError as exc:
            db.commit()
            raise AppError(503, "email_failed", "We couldn't send the email.") from exc
    db.commit()


def check_code(db: Session, gym: Gym, where: Destination, code: str) -> OtpCode:
    """The live code row, if `code` is right. Counts wrong tries."""
    row = db.scalars(
        select(OtpCode)
        .where(
            OtpCode.gym_id == gym.id,
            OtpCode.destination == where.value,
            OtpCode.consumed_at.is_(None),
            OtpCode.expires_at > utcnow(),
        )
        .order_by(OtpCode.created_at.desc())
        .with_for_update()
    ).first()
    wrong = AppError(401, "bad_code", "That code is wrong or has expired.")
    if row is None or row.attempts >= settings.otp_max_attempts:
        raise wrong
    if not hmac.compare_digest(row.code_hash, _hash(gym.id, where, code.strip())):
        row.attempts += 1
        db.commit()
        raise wrong
    return row


# --- sessions ---------------------------------------------------------------------


@dataclass
class Issued:
    member: Member
    session: MemberSession
    access_token: str
    refresh_token: str | None


def _access_token(member: Member, session: MemberSession) -> str:
    return create_member_token(
        member_id=member.id, gym_id=member.gym_id, session_id=session.id
    )


def start_session(db: Session, member: Member, request: Request | None) -> Issued:
    raw = new_refresh_token()
    session = MemberSession(
        member_id=member.id,
        refresh_token_hash=hash_refresh_token(raw),
        device_label=(request.headers.get("User-Agent", "")[:255] if request else None),
        expires_at=utcnow() + dt.timedelta(days=settings.member_refresh_days),
        last_used_at=utcnow(),
    )
    db.add(session)
    db.flush()
    return Issued(member, session, _access_token(member, session), raw)


def refresh(db: Session, raw: str | None) -> Issued | None:
    if not raw:
        return None
    now = utcnow()
    token_hash = hash_refresh_token(raw)
    session = db.scalars(
        select(MemberSession)
        .where(
            or_(
                MemberSession.refresh_token_hash == token_hash,
                MemberSession.previous_token_hash == token_hash,
            )
        )
        .with_for_update()
    ).first()
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        return None
    member = db.get(Member, session.member_id)
    if member is None or not member.app_access:
        return None
    session.last_used_at = now
    if session.refresh_token_hash != token_hash:
        if session.rotated_at is None or now - session.rotated_at > ROTATION_GRACE:
            return None
        return Issued(member, session, _access_token(member, session), None)
    fresh = new_refresh_token()
    session.previous_token_hash = token_hash
    session.refresh_token_hash = hash_refresh_token(fresh)
    session.rotated_at = now
    db.flush()
    return Issued(member, session, _access_token(member, session), fresh)


def revoke(db: Session, raw: str | None) -> None:
    if not raw:
        return
    token_hash = hash_refresh_token(raw)
    for session in db.scalars(
        select(MemberSession).where(
            or_(
                MemberSession.refresh_token_hash == token_hash,
                MemberSession.previous_token_hash == token_hash,
            ),
            MemberSession.revoked_at.is_(None),
        )
    ):
        session.revoked_at = utcnow()


def sign_out_everywhere(db: Session, member_id: uuid.UUID) -> int:
    """Lost phone, access turned off, phone or email changed (§5.5).

    Through the ORM rather than one bulk UPDATE, so session objects already
    loaded in this request see the revocation too. A member has few sessions.
    """
    sessions = db.scalars(
        select(MemberSession).where(
            MemberSession.member_id == member_id, MemberSession.revoked_at.is_(None)
        )
    ).all()
    now = utcnow()
    for session in sessions:
        session.revoked_at = now
    db.flush()
    return len(sessions)
