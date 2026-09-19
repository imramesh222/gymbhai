"""Every background job the worker runs (PLAN.md §9), registered in one place."""

import datetime as dt

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.job import Job
from app.models.member_app import MemberSession, OtpCode
from app.models.staff import StaffSession
from app.services import reminders
from app.services.sms import service as sms
from app.worker import DAILY, handler

JOB_CLEANUP = "maintenance.cleanup"

handler(sms.JOB_SEND, on_give_up=sms.give_up)(sms.handle_send)
handler(reminders.JOB_DAILY)(reminders.handle_daily)


@handler(JOB_CLEANUP)
def cleanup(db: Session, payload: dict) -> None:
    """Finished jobs older than a month, used-up sign-in codes, dead sessions."""
    now = utcnow()
    db.execute(delete(Job).where(Job.done_at < now - dt.timedelta(days=30)))
    # Kept a day past expiry: the rate limits count recent codes.
    db.execute(delete(OtpCode).where(OtpCode.expires_at < now - dt.timedelta(days=1)))
    for model in (MemberSession, StaffSession):
        db.execute(delete(model).where(model.expires_at < now - dt.timedelta(days=7)))


DAILY.extend(
    [
        (reminders.JOB_DAILY, dt.time(9, 0)),
        (JOB_CLEANUP, dt.time(3, 0)),
    ]
)
