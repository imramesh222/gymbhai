"""Queueing SMS, sending them from the worker, and the credits they cost.

* Every SMS is a row in sms_messages, queued as a job and sent by the worker,
  which retries gateway failures with backoff (PLAN.md §9).
* Credits are counted in SMS parts. A gym with no credit left gets its message
  marked `no_credit`, and nothing else stops working (§5.7).
* Sign-in codes are never charged to the gym and never blocked by credit;
  they are on us (§5.7), and sent at once rather than queued (§9).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.sms_text import segments
from app.core.time import utcnow
from app.models.gym import Gym
from app.models.messaging import (
    FREE_KINDS,
    SMS_FAILED,
    SMS_NO_CREDIT,
    SMS_QUEUED,
    SMS_SENT,
    SmsCreditLedger,
    SmsMessage,
)
from app.services.sms.providers import SmsError, SmsRejected, get_provider

JOB_SEND = "sms.send"


def balance(db: Session, gym_id: uuid.UUID) -> int:
    """The sum of every change. Not "the latest balance_after": Postgres's now()
    is fixed for a whole transaction, so rows written together tie on time and
    "latest" would be a coin toss. balance_after is kept for people reading
    the ledger."""
    return (
        db.scalar(
            select(func.coalesce(func.sum(SmsCreditLedger.change), 0)).where(
                SmsCreditLedger.gym_id == gym_id
            )
        )
        or 0
    )


def _lock_gym(db: Session, gym_id: uuid.UUID) -> None:
    """Serialise credit changes for one gym: two sends can't spend one credit."""
    db.execute(select(Gym.id).where(Gym.id == gym_id).with_for_update())


def add_credits(
    db: Session, gym_id: uuid.UUID, change: int, reason: str
) -> SmsCreditLedger:
    _lock_gym(db, gym_id)
    row = SmsCreditLedger(
        gym_id=gym_id,
        change=change,
        reason=reason,
        balance_after=balance(db, gym_id) + change,
    )
    db.add(row)
    db.flush()
    return row


def queue(
    db: Session,
    *,
    gym_id: uuid.UUID,
    to: str,
    body: str,
    kind: str,
    member_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
) -> SmsMessage:
    """Add an SMS to send once the caller's transaction commits."""
    from app.worker import enqueue

    message = SmsMessage(
        gym_id=gym_id,
        member_id=member_id,
        to=to,
        body=body,
        kind=kind,
        status=SMS_QUEUED,
        segments=segments(body),
        created_by=created_by,
    )
    db.add(message)
    db.flush()
    enqueue(db, JOB_SEND, {"sms_id": str(message.id)})
    return message


def deliver(db: Session, message: SmsMessage) -> None:
    """Send one message now. Raises SmsError for the worker to retry."""
    if message.status != SMS_QUEUED:
        return
    charged = message.kind not in FREE_KINDS
    if charged:
        _lock_gym(db, message.gym_id)
        if balance(db, message.gym_id) < message.segments:
            message.status = SMS_NO_CREDIT
            message.error = "No SMS credit left."
            return

    provider = get_provider()
    result = provider.send(message.to, message.body)

    message.status = SMS_SENT
    message.provider = provider.name
    message.provider_ref = result.provider_ref
    message.sent_at = utcnow()
    message.error = None
    if charged:
        db.add(
            SmsCreditLedger(
                gym_id=message.gym_id,
                change=-message.segments,
                reason=f"sms:{message.kind}",
                balance_after=balance(db, message.gym_id) - message.segments,
                sms_message_id=message.id,
            )
        )


def send_now(db: Session, message: SmsMessage) -> bool:
    """For sign-in codes: no queue behind reminders. True if it went."""
    try:
        deliver(db, message)
        return message.status == SMS_SENT
    except SmsError as exc:
        message.status = SMS_FAILED
        message.error = str(exc)[:500]
        return False


def handle_send(db: Session, payload: dict) -> None:
    message = db.get(SmsMessage, uuid.UUID(payload["sms_id"]))
    if message is None:
        return
    try:
        deliver(db, message)
    except SmsRejected as exc:
        # The gateway refused the message itself (bad number, bad sender, bad
        # token): the same message would be refused again, so it is marked
        # failed here rather than retried for half an hour first.
        message.status = SMS_FAILED
        message.error = str(exc)[:500]


def give_up(db: Session, payload: dict, error: str) -> None:
    message = db.get(SmsMessage, uuid.UUID(payload["sms_id"]))
    if message is not None and message.status == SMS_QUEUED:
        message.status = SMS_FAILED
        message.error = error[-500:]
