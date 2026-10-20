"""Messages to members: by push first, then WhatsApp, then SMS (PLAN.md
§16.3 8.3, §19.3).

`notify` is how a reminder, a notice or an answer to a payment request
reaches a member. A member with a working subscription gets a push, which
costs nothing. The rest get a WhatsApp message, when the message has one of
our approved templates, the gym turned WhatsApp on and the member agreed;
otherwise an SMS. Both use credits. A gym can ask for both push and a message
("Also send SMS"). The push itself goes from the worker: if every phone the
member had turns out to be gone, the WhatsApp message or SMS is sent instead.

Sign-in codes and messages typed at the desk stay SMS: they were asked for as
SMS. The welcome skips push (they can't have the app yet) and goes by WhatsApp
or SMS (`paid_message`).
"""

import uuid
from collections.abc import Iterable
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.push_keys import public_key
from app.core.time import utcnow
from app.core.whatsapp_templates import WhatsApp
from app.models.gym import Gym
from app.models.member import Member
from app.models.messaging import SmsMessage
from app.models.push import KIND_EXPO, KIND_WEB, PushSubscription
from app.services.push.providers import (
    PushError,
    PushGone,
    PushMessage,
    Target,
    get_provider,
)
from app.services.sms import service as sms
from app.services.whatsapp import service as whatsapp_service

JOB_PUSH = "push.send"

Channel = Literal["push", "sms", "whatsapp", "both"]


def available() -> bool:
    """Web Push needs our VAPID key; without one, browsers get SMS instead.
    The phone app's push (Expo) needs no key of ours, so it always works."""
    return public_key() is not None


def _usable():
    """Subscriptions we can send to now: the app's always, browsers' with a key."""
    alive = PushSubscription.revoked_at.is_(None)
    if available():
        return alive
    return alive & (PushSubscription.kind == KIND_EXPO)


def live(db: Session, member_id: uuid.UUID) -> list[PushSubscription]:
    return list(
        db.scalars(
            select(PushSubscription).where(
                PushSubscription.member_id == member_id,
                PushSubscription.revoked_at.is_(None),
            )
        )
    )


def reachable(db: Session, member_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    """Which of these members have a phone that takes push: one query."""
    ids = list(member_ids)
    if not ids:
        return set()
    return set(
        db.scalars(
            select(PushSubscription.member_id)
            .where(PushSubscription.member_id.in_(ids), _usable())
            .distinct()
        )
    )


def reachable_in_gym(db: Session, gym_id: uuid.UUID) -> set[uuid.UUID]:
    """Every member of the gym who takes push: for the daily automations."""
    return set(
        db.scalars(
            select(PushSubscription.member_id)
            .where(PushSubscription.gym_id == gym_id, _usable())
            .distinct()
        )
    )


def subscribe(
    db: Session,
    member: Member,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str | None,
) -> PushSubscription:
    """This phone takes reminders now. The same phone again replaces its keys."""
    row = db.scalar(
        select(PushSubscription).where(
            PushSubscription.member_id == member.id,
            PushSubscription.endpoint == endpoint,
        )
    )
    if row is None:
        row = PushSubscription(
            gym_id=member.gym_id, member_id=member.id, endpoint=endpoint
        )
        db.add(row)
    row.kind = KIND_WEB
    row.p256dh = p256dh
    row.auth = auth
    row.user_agent = (user_agent or "")[:300] or None
    row.revoked_at = None
    db.flush()
    return row


def subscribe_app(
    db: Session, member: Member, *, expo_token: str, user_agent: str | None
) -> PushSubscription:
    """The phone app takes notifications (§17.6). The same token again: no change."""
    row = db.scalar(
        select(PushSubscription).where(
            PushSubscription.member_id == member.id,
            PushSubscription.expo_token == expo_token,
        )
    )
    if row is None:
        row = PushSubscription(
            gym_id=member.gym_id,
            member_id=member.id,
            kind=KIND_EXPO,
            expo_token=expo_token,
        )
        db.add(row)
    row.user_agent = (user_agent or "")[:300] or None
    row.revoked_at = None
    db.flush()
    return row


def unsubscribe(
    db: Session,
    member: Member,
    endpoint: str | None = None,
    expo_token: str | None = None,
) -> int:
    """Turn this phone off (or, with neither, every phone). Returns how many."""
    everything = endpoint is None and expo_token is None
    rows = [
        r
        for r in live(db, member.id)
        if everything
        or (endpoint is not None and r.endpoint == endpoint)
        or (expo_token is not None and r.expo_token == expo_token)
    ]
    for row in rows:
        row.revoked_at = utcnow()
    return len(rows)


def notify(
    db: Session,
    gym: Gym,
    member: Member,
    *,
    title: str,
    body: str,
    url: str,
    sms_body: str,
    sms_kind: str,
    tag: str | None = None,
    created_by: uuid.UUID | None = None,
    pushable: set[uuid.UUID] | None = None,
    flush: bool = True,
    sms_allowed: bool = True,
    whatsapp: WhatsApp | None = None,
) -> tuple[Channel | None, SmsMessage | None]:
    """Reach a member: push if they can take it, else (or also) a WhatsApp
    message or an SMS.

    `pushable` is `reachable(...)` worked out once for a bulk send.
    `whatsapp` is the template to use if WhatsApp can carry it (§19.3).
    `sms_allowed=False` is push only, which is free: a member without push
    isn't reached (None), and a push that fails sends nothing instead.
    Returns how, and the message (SMS or WhatsApp) queued now, if any.
    """
    from app.worker import enqueue

    can_push = (
        member.id in pushable
        if pushable is not None
        else bool(reachable(db, [member.id]))
    )
    if not can_push and not sms_allowed:
        return None, None
    also_sms = gym.config.also_sms and sms_allowed
    message = None
    if not can_push or also_sms:
        message = paid_message(
            db,
            gym,
            member,
            sms_body=sms_body,
            sms_kind=sms_kind,
            whatsapp=whatsapp,
            created_by=created_by,
            flush=flush,
        )
    if can_push:
        enqueue(
            db,
            JOB_PUSH,
            {
                "member_id": str(member.id),
                "title": title,
                "body": body,
                "url": url,
                "tag": tag,
                # The SMS to send if no phone takes it; none if one went already.
                "fallback": None
                if message or not sms_allowed
                else {
                    "body": sms_body,
                    "kind": sms_kind,
                    "created_by": str(created_by) if created_by else None,
                    "whatsapp": whatsapp.payload() if whatsapp else None,
                },
            },
        )
    if can_push:
        return "both" if message else "push", message
    assert message is not None
    return "whatsapp" if message.channel == "whatsapp" else "sms", message


def paid_message(
    db: Session,
    gym: Gym,
    member: Member,
    *,
    sms_body: str,
    sms_kind: str,
    whatsapp: WhatsApp | None = None,
    created_by: uuid.UUID | None = None,
    flush: bool = True,
) -> SmsMessage:
    """By WhatsApp if it can carry it (§19.3), else SMS. Both cost credits."""
    if whatsapp is not None and whatsapp_service.reachable(gym, member):
        return whatsapp_service.queue(
            db,
            gym,
            member,
            whatsapp,
            kind=sms_kind,
            fallback=sms_body,
            created_by=created_by,
            flush=flush,
        )
    return sms.queue(
        db,
        gym_id=gym.id,
        to=member.phone,
        body=sms_body,
        kind=sms_kind,
        member_id=member.id,
        created_by=created_by,
        flush=flush,
    )


def _fallback(db: Session, payload: dict) -> None:
    fallback = payload.get("fallback")
    member = db.get(Member, uuid.UUID(payload["member_id"]))
    if not fallback or member is None:
        return
    gym = db.get(Gym, member.gym_id)
    assert gym is not None
    paid_message(
        db,
        gym,
        member,
        sms_body=fallback["body"],
        sms_kind=fallback["kind"],
        whatsapp=WhatsApp.from_payload(fallback["whatsapp"])
        if fallback.get("whatsapp")
        else None,
        created_by=uuid.UUID(fallback["created_by"])
        if fallback.get("created_by")
        else None,
    )


def handle_send(db: Session, payload: dict) -> None:
    """The worker's half: every live phone of the member, then the SMS if none took it.

    A push service that fails for now makes the job retry (unless a phone
    already took it); one that says the subscription is gone revokes it.
    """
    message = PushMessage(
        title=payload["title"],
        body=payload["body"],
        url=payload["url"],
        tag=payload.get("tag"),
    )
    delivered = False
    failed: PushError | None = None
    for row in live(db, uuid.UUID(payload["member_id"])):
        if row.kind == KIND_WEB and not available():
            continue
        target = Target(row.endpoint, row.p256dh, row.auth, row.expo_token)
        try:
            get_provider(target).send(target, message)
        except PushGone:
            row.revoked_at = utcnow()
        except PushError as exc:
            failed = exc
        else:
            row.last_ok_at = utcnow()
            delivered = True
    if delivered:
        return
    if failed is not None:
        raise failed  # retried; on giving up, give_up sends the SMS
    _fallback(db, payload)


def give_up(db: Session, payload: dict, error: str) -> None:
    _fallback(db, payload)
