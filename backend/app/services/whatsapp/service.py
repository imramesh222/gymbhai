"""WhatsApp messages to members, between push and SMS (PLAN.md §19.3).

* `notify` (app/services/push/service.py) tries push, then WhatsApp where the
  gym turned it on and the member agreed, then SMS. Only messages with one of
  our approved templates (app/core/whatsapp_templates.py) can go by WhatsApp.
* A WhatsApp message is a row in sms_messages with channel "whatsapp", sent by
  the worker like an SMS. It costs the gym the credits set in /admin
  (platform_settings), charged when Meta takes it and given back if Meta
  later reports it failed.
* Whatever WhatsApp can't deliver goes by SMS instead: the row keeps the SMS
  it stands in for. When Meta says a number isn't on WhatsApp, WhatsApp isn't
  tried for that number at that gym for UNREACHABLE_DAYS.
* Meta's webhook reports each message delivered, read or failed, and passes
  on what members write back. There is no inbox: at most once a day a member
  is told where to reach their gym, and "STOP" turns WhatsApp off.
"""

import datetime as dt
import hashlib
import hmac
import logging
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.phone import normalize_phone
from app.core.time import utcnow
from app.core.whatsapp_templates import TEMPLATES, WhatsApp, meta_language
from app.models.activity import ACTOR_SYSTEM
from app.models.billing import PlatformSettings
from app.models.gym import Gym
from app.models.member import Member
from app.models.messaging import (
    CHANNEL_WHATSAPP,
    FREE_KINDS,
    SMS_FAILED,
    SMS_NO_CREDIT,
    SMS_QUEUED,
    SMS_REPLY,
    SMS_SENT,
    SmsCreditLedger,
    SmsMessage,
)
from app.services import activity, live
from app.services.sms import service as sms
from app.services.whatsapp.providers import (
    NotOnWhatsApp,
    Outgoing,
    WhatsAppRejected,
    failure,
    get_provider,
)

log = logging.getLogger("gymbhai.whatsapp")

JOB_SEND = "whatsapp.send"
UNREACHABLE_DAYS = 30
# Meta lets a business answer freely for 24 hours after a member writes.
REPLY_EVERY = dt.timedelta(hours=24)
STOP_WORDS = {"stop", "unsubscribe", "रोक", "रोक्नुहोस्", "बन्द"}


def available() -> bool:
    """Whether WhatsApp can send at all. On a server only with Meta set up:
    the console there would mark messages sent that nobody receives."""
    return settings.whatsapp_provider == "meta" or settings.environment in (
        "local",
        "test",
    )


def platform_settings(db: Session) -> PlatformSettings:
    """Our one row of settings, made the first time it's needed."""
    row = db.scalar(select(PlatformSettings).order_by(PlatformSettings.created_at))
    if row is None:
        row = PlatformSettings(whatsapp_credits=1)
        db.add(row)
        db.flush()
    return row


def credits_each(db: Session) -> int:
    """What one WhatsApp message costs a gym, read once per session: a daily
    run sends hundreds."""
    if "whatsapp_credits" not in db.info:
        db.info["whatsapp_credits"] = platform_settings(db).whatsapp_credits
    return db.info["whatsapp_credits"]


def reachable(gym: Gym, member: Member, now: dt.datetime | None = None) -> bool:
    """WhatsApp may carry this member's messages: the gym has it on, they
    agreed, and Meta hasn't lately said their number isn't on WhatsApp."""
    if not (
        available()
        and gym.config.whatsapp
        and member.whatsapp_agreed_at is not None
        and member.erased_at is None
    ):
        return False
    gone = member.whatsapp_unreachable_at
    return gone is None or gone < (now or utcnow()) - dt.timedelta(
        days=UNREACHABLE_DAYS
    )


def queue(
    db: Session,
    gym: Gym,
    member: Member,
    message: WhatsApp,
    *,
    kind: str,
    fallback: str | None,
    created_by: uuid.UUID | None = None,
    flush: bool = True,
) -> SmsMessage:
    """A WhatsApp message to send once the caller's transaction commits;
    `fallback` is the SMS to send if WhatsApp can't deliver it."""
    from app.worker import enqueue

    template = TEMPLATES[message.template]
    language, code = meta_language(member.language or gym.config.language)
    row = SmsMessage(
        id=uuid.uuid4(),
        gym_id=gym.id,
        member_id=member.id,
        to=member.phone,
        body=template.render(language, message.values),
        kind=kind,
        status=SMS_QUEUED,
        segments=credits_each(db),
        channel=CHANNEL_WHATSAPP,
        template=template.name,
        params={
            "language": code,
            "values": template.values(language, message.values),
            "button": message.button,
        },
        fallback=fallback,
        created_by=created_by,
    )
    db.add(row)
    if flush:
        db.flush()
    enqueue(db, JOB_SEND, {"sms_id": str(row.id)})
    return row


def _charge(db: Session, message: SmsMessage, change: int, reason: str) -> None:
    db.add(
        SmsCreditLedger(
            gym_id=message.gym_id,
            change=change,
            reason=reason,
            balance_after=sms.balance(db, message.gym_id) + change,
            sms_message_id=message.id,
        )
    )


def _fallback(db: Session, message: SmsMessage) -> None:
    """The SMS this message stood in for, if it had one."""
    if message.fallback and message.member_id is not None:
        sms.queue(
            db,
            gym_id=message.gym_id,
            to=message.to,
            body=message.fallback,
            kind=message.kind,
            member_id=message.member_id,
            created_by=message.created_by,
        )


def _unreachable(db: Session, message: SmsMessage) -> None:
    """Not on WhatsApp: everyone at the gym with that number, as it's the
    number that isn't."""
    for member in db.scalars(
        select(Member).where(
            Member.gym_id == message.gym_id, Member.phone == message.to
        )
    ):
        member.whatsapp_unreachable_at = utcnow()


def _failed(db: Session, message: SmsMessage, error: Exception) -> None:
    message.status = SMS_FAILED
    message.error = str(error)[:500]
    if isinstance(error, NotOnWhatsApp):
        _unreachable(db, message)
    _fallback(db, message)
    live.publish(db, gym_id=message.gym_id, kind=live.MESSAGE)


def deliver(db: Session, message: SmsMessage) -> None:
    """Send one message now. Raises WhatsAppError for the worker to retry."""
    if message.status != SMS_QUEUED:
        return
    charged = message.kind not in FREE_KINDS
    if charged:
        sms.lock_gym(db, message.gym_id)
        if sms.balance(db, message.gym_id) < message.segments:
            message.status = SMS_NO_CREDIT
            message.error = "No message credit left."
            live.publish(db, gym_id=message.gym_id, kind=live.MESSAGE)
            return
    provider = get_provider()
    try:
        if message.template is None:
            result = provider.send_text(message.to, message.body)
        else:
            params = message.params or {}
            result = provider.send_template(
                Outgoing(
                    to=message.to,
                    template=message.template,
                    language=params.get("language", "en"),
                    values=list(params.get("values") or []),
                    button=params.get("button"),
                )
            )
    except WhatsAppRejected as exc:
        _failed(db, message, exc)
        return
    message.status = SMS_SENT
    message.provider = provider.name
    message.provider_ref = result.provider_ref
    message.sent_at = utcnow()
    message.error = None
    if charged:
        _charge(db, message, -message.segments, f"whatsapp:{message.kind}")
    live.publish(db, gym_id=message.gym_id, kind=live.MESSAGE)


def handle_send(db: Session, payload: dict) -> None:
    message = db.get(SmsMessage, uuid.UUID(payload["sms_id"]))
    if message is not None:
        deliver(db, message)


def give_up(db: Session, payload: dict, error: str) -> None:
    """Meta kept failing: the SMS goes instead."""
    message = db.get(SmsMessage, uuid.UUID(payload["sms_id"]))
    if message is not None and message.status == SMS_QUEUED:
        _failed(db, message, RuntimeError(error[-500:]))


# --- Meta's webhook -----------------------------------------------------------------


def signature_ok(body: bytes, header: str | None) -> bool:
    """Meta signs every call with our app secret (X-Hub-Signature-256). With
    no secret set, nothing is accepted."""
    secret = settings.whatsapp_app_secret
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def receive(db: Session, payload: dict) -> None:
    """Everything in one webhook call: delivery reports and members' messages."""
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for status in value.get("statuses") or []:
                on_status(db, status)
            for message in value.get("messages") or []:
                on_message(db, message)


def _at(timestamp: object) -> dt.datetime:
    try:
        return dt.datetime.fromtimestamp(int(str(timestamp)), dt.UTC)
    except (TypeError, ValueError):
        return utcnow()


def on_status(db: Session, status: dict) -> None:
    """Delivered, read or failed. Reports can come twice or out of order."""
    wamid = status.get("id")
    if not wamid:
        return
    message = db.scalar(
        select(SmsMessage)
        .where(
            SmsMessage.provider_ref == wamid,
            SmsMessage.channel == CHANNEL_WHATSAPP,
        )
        .with_for_update()
    )
    if message is None:
        return
    at = _at(status.get("timestamp"))
    state = status.get("status")
    if state in ("delivered", "read") and message.status == SMS_SENT:
        message.delivered_at = message.delivered_at or at
        if state == "read":
            message.read_at = message.read_at or at
    elif state == "failed" and message.status == SMS_SENT:
        error = failure(400, (status.get("errors") or [{}])[0])
        if message.kind not in FREE_KINDS:
            sms.lock_gym(db, message.gym_id)
            _charge(db, message, message.segments, "whatsapp:refund")
        _failed(db, message, error)
        return
    else:
        return
    live.publish(db, gym_id=message.gym_id, kind=live.MESSAGE)


def on_message(db: Session, message: dict) -> None:
    """A member wrote to our number: STOP, or once a day where to reach the gym."""
    try:
        phone = normalize_phone(str(message.get("from") or ""))
    except ValueError:
        return
    said = ""
    if message.get("type") == "text":
        said = (message.get("text") or {}).get("body") or ""
    elif message.get("type") == "button":
        said = (message.get("button") or {}).get("text") or ""
    # Two messages at once from one number answer once.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"whatsapp:{phone}"},
    )
    last = db.scalar(
        select(SmsMessage)
        .where(
            SmsMessage.to == phone,
            SmsMessage.channel == CHANNEL_WHATSAPP,
            SmsMessage.kind != SMS_REPLY,
            SmsMessage.status == SMS_SENT,
        )
        .order_by(SmsMessage.created_at.desc())
        .limit(1)
    )
    if last is None:
        return  # we never wrote to them: not ours to answer
    gym = db.get(Gym, last.gym_id)
    member = db.get(Member, last.member_id) if last.member_id else None
    assert gym is not None
    language = (member.language if member else None) or gym.config.language
    if said.strip().lower() in STOP_WORDS:
        stopped = stop(db, phone)
        _reply(db, gym, member, phone, STOPPED[language].format(gym=gym.name))
        log.info("WhatsApp: %s stopped (%d members)", phone, stopped)
        return
    replied = db.scalar(
        select(func.count())
        .select_from(SmsMessage)
        .where(
            SmsMessage.to == phone,
            SmsMessage.channel == CHANNEL_WHATSAPP,
            SmsMessage.kind == SMS_REPLY,
            SmsMessage.created_at > utcnow() - REPLY_EVERY,
        )
    )
    if not replied:
        _reply(db, gym, member, phone, reply_text(gym, language))


STOPPED = {
    "en": "You won't get WhatsApp messages from {gym} or other GymBhai gyms any "
    "more. To have them again, turn WhatsApp on in your gym's app.",
    "ne": "अब तपाईंलाई {gym} वा अरू GymBhai जिमबाट WhatsApp सन्देश आउँदैन। फेरि "
    "चाहिए जिमको एपमा WhatsApp खोल्नुहोस्।",
}

REPLY = {
    "en": "This number only sends messages from {gym}. To reach them, {how}",
    "ne": "यो नम्बरबाट {gym} का सन्देश मात्र पठाइन्छ। उहाँहरूलाई सम्पर्क गर्न {how}",
}
REPLY_HOW = {
    "en": ("message them on {link}", "please contact the gym directly."),
    "ne": ("{link} मा सन्देश पठाउनुहोस्।", "कृपया जिममै सम्पर्क गर्नुहोस्।"),
}


def reply_text(gym: Gym, language: str) -> str:
    with_phone, without = REPLY_HOW[language]
    how = (
        with_phone.format(link=f"https://wa.me/977{gym.phone}")
        if gym.phone
        else without
    )
    return REPLY[language].format(gym=gym.name, how=how)


def _reply(
    db: Session, gym: Gym, member: Member | None, phone: str, body: str
) -> SmsMessage:
    """A free-form answer inside Meta's 24 hours: on us, never the gym's credit."""
    from app.worker import enqueue

    row = SmsMessage(
        id=uuid.uuid4(),
        gym_id=gym.id,
        member_id=member.id if member else None,
        to=phone,
        body=body,
        kind=SMS_REPLY,
        status=SMS_QUEUED,
        segments=0,
        channel=CHANNEL_WHATSAPP,
    )
    db.add(row)
    db.flush()
    enqueue(db, JOB_SEND, {"sms_id": str(row.id)})
    return row


def stop(db: Session, phone: str) -> int:
    """STOP: every member with that number, at every gym, stops getting
    WhatsApp. One number writes to us for all of them. Returns how many."""
    members = list(
        db.scalars(
            select(Member).where(
                Member.phone == phone, Member.whatsapp_agreed_at.is_not(None)
            )
        )
    )
    for member in members:
        member.whatsapp_agreed_at = None
        activity.record(
            db,
            gym_id=member.gym_id,
            actor_type=ACTOR_SYSTEM,
            actor_id=None,
            action="member.whatsapp_stopped",
            entity="member",
            entity_id=member.id,
            changes={"whatsapp_agreed": {"before": True, "after": False}},
        )
        live.member_changed(db, member.gym_id, member.id, member.home_branch_id)
    return len(members)
