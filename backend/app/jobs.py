"""Every background job the worker runs (PLAN.md §9), registered in one place."""

import datetime as dt

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.idempotency import IdempotencyKey
from app.models.job import Job
from app.models.lead import Lead
from app.models.member_app import MemberSession, MemberSignInLink, OtpCode
from app.models.staff import LoginAttempt, StaffPasswordReset, StaffSession
from app.services import classes, online_payments, owner_messages, reminders, tax
from app.services.push import service as push
from app.services.push import staff as staff_push
from app.services.sms import service as sms
from app.services.whatsapp import service as whatsapp
from app.worker import DAILY, handler

JOB_CLEANUP = "maintenance.cleanup"

handler(sms.JOB_SEND, on_give_up=sms.give_up)(sms.handle_send)
handler(whatsapp.JOB_SEND, on_give_up=whatsapp.give_up)(whatsapp.handle_send)
handler(push.JOB_PUSH, on_give_up=push.give_up)(push.handle_send)
handler(staff_push.JOB_STAFF_PUSH)(staff_push.handle_send)
handler(reminders.JOB_DAILY)(reminders.handle_daily)
handler(classes.JOB_GENERATE)(classes.handle_generate)
handler(classes.JOB_REMINDER)(classes.handle_reminder)
handler(online_payments.JOB_CHECK)(online_payments.handle_check)
handler(tax.JOB_CBMS, on_give_up=tax.give_up_cbms)(tax.handle_cbms)
handler(owner_messages.JOB_SUBSCRIPTION)(
    lambda db, payload: owner_messages.subscription_reminders(db)
)
handler(owner_messages.JOB_SETUP_NUDGE)(
    lambda db, payload: owner_messages.setup_nudges(db)
)
handler(owner_messages.JOB_SUMMARY)(
    lambda db, payload: owner_messages.daily_summaries(db)
)


@handler(JOB_CLEANUP)
def cleanup(db: Session, payload: dict) -> None:
    """Finished jobs older than a month, used-up sign-in and password reset
    codes, old sign-in tries and idempotency keys, dead sessions."""
    now = utcnow()
    db.execute(delete(Job).where(Job.done_at < now - dt.timedelta(days=30)))
    # Kept a day past expiry: the rate limits count recent codes. (Desk QRs
    # have no limits to count, but a day leaves who-used-what for a question.)
    for code in (OtpCode, StaffPasswordReset, MemberSignInLink):
        db.execute(delete(code).where(code.expires_at < now - dt.timedelta(days=1)))
    db.execute(delete(LoginAttempt).where(LoginAttempt.at < now - dt.timedelta(days=1)))
    # A repeat of a money request comes within minutes, not days.
    db.execute(
        delete(IdempotencyKey).where(
            IdempotencyKey.created_at < now - dt.timedelta(days=1)
        )
    )
    # The join form's sender IPs are for its rate limit only (§16.4, 9.5).
    db.execute(
        update(Lead)
        .where(Lead.from_ip.is_not(None), Lead.created_at < now - dt.timedelta(days=1))
        .values(from_ip=None)
    )
    for model in (MemberSession, StaffSession):
        db.execute(delete(model).where(model.expires_at < now - dt.timedelta(days=7)))


DAILY.extend(
    [
        (reminders.JOB_DAILY, dt.time(9, 0)),
        # The timetable's classes, 4 weeks ahead (§19.4).
        (classes.JOB_GENERATE, dt.time(1, 0)),
        (JOB_CLEANUP, dt.time(3, 0)),
        (owner_messages.JOB_SUBSCRIPTION, dt.time(10, 0)),
        (owner_messages.JOB_SETUP_NUDGE, dt.time(10, 30)),
        (owner_messages.JOB_SUMMARY, dt.time(20, 0)),
    ]
)
