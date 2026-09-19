"""The background worker (PLAN.md §9): `python -m app.worker`.

Jobs are rows in `jobs`, claimed with FOR UPDATE SKIP LOCKED so several
workers can run side by side without taking the same job. A job's handler does
its work in the session it is given; the worker commits, so a job's effects
and its "done" mark are saved together.

Handlers register with @handler("kind") in app/jobs.py. A handler may name an
`on_give_up` to run, in a fresh transaction, when a job fails for good.

Daily tasks (DAILY) are queued once per Nepal day by whichever worker gets
there first; the unique (name, run_on) row in scheduled_runs decides.
"""

import datetime as dt
import logging
import signal
import threading
import traceback
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utcnow
from app.models.job import Job

log = logging.getLogger("gymbhai.worker")

Handler = Callable[[Session, dict[str, Any]], None]
GiveUp = Callable[[Session, dict[str, Any], str], None]
HANDLERS: dict[str, Handler] = {}
GIVE_UP: dict[str, GiveUp] = {}

# (job kind, Nepal time of day). Queued once per day at or after that time.
DAILY: list[tuple[str, dt.time]] = []

# One try and three retries (PLAN.md §9: "retry failures 3 times").
MAX_ATTEMPTS = 4
# A job locked longer than this belongs to a worker that died mid-job.
LOCK_TIMEOUT = dt.timedelta(minutes=10)


def handler(
    kind: str, *, on_give_up: GiveUp | None = None
) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        if kind in HANDLERS:
            raise ValueError(f"Two handlers for job kind {kind!r}.")
        HANDLERS[kind] = fn
        if on_give_up is not None:
            GIVE_UP[kind] = on_give_up
        return fn

    return register


def queue_daily(db: Session, now: dt.datetime | None = None) -> list[str]:
    """Queue today's daily tasks whose time has come. Returns their kinds."""
    from sqlalchemy.dialects.postgresql import insert

    from app.core.time import NEPAL
    from app.models.messaging import ScheduledRun

    local = (now or utcnow()).astimezone(NEPAL)
    queued = []
    for kind, at in DAILY:
        if local.time() < at:
            continue
        inserted = db.execute(
            insert(ScheduledRun)
            .values(id=uuid.uuid4(), name=kind, run_on=local.date())
            .on_conflict_do_nothing()
            .returning(ScheduledRun.id)
        ).scalar()
        if inserted:
            enqueue(db, kind, {"date": local.date().isoformat()})
            queued.append(kind)
    db.commit()
    return queued


def enqueue(
    db: Session,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    run_at: dt.datetime | None = None,
) -> Job:
    """Add a job in the caller's transaction; it runs once that commits."""
    job = Job(kind=kind, payload=payload or {}, run_at=run_at or utcnow())
    db.add(job)
    return job


def backoff(attempts: int) -> dt.timedelta:
    """1, 5, then 25 minutes."""
    return dt.timedelta(minutes=5 ** (attempts - 1))


def claim(db: Session, limit: int = 20) -> list[uuid.UUID]:
    now = utcnow()
    jobs = db.scalars(
        select(Job)
        .where(
            Job.done_at.is_(None),
            Job.run_at <= now,
            or_(Job.locked_at.is_(None), Job.locked_at < now - LOCK_TIMEOUT),
        )
        .order_by(Job.run_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    for job in jobs:
        job.locked_at = now
    db.commit()
    return [job.id for job in jobs]


def execute(db: Session, job_id: uuid.UUID) -> bool:
    """Run one claimed job. True if it succeeded."""
    job = db.get(Job, job_id)
    if job is None or job.done_at is not None:
        return False
    run = HANDLERS.get(job.kind)
    try:
        if run is None:
            raise LookupError(f"No handler for job kind {job.kind!r}.")
        run(db, dict(job.payload))
    except Exception:
        error = traceback.format_exc(limit=5)
        db.rollback()
        _record_failure(db, job_id, error)
        return False

    job.done_at = utcnow()
    job.locked_at = None
    job.error = None
    db.commit()
    return True


def _record_failure(db: Session, job_id: uuid.UUID, error: str) -> None:
    job = db.get(Job, job_id)
    if job is None:
        return
    now = utcnow()
    job.attempts += 1
    job.error = error
    job.locked_at = None
    if job.attempts >= MAX_ATTEMPTS or job.kind not in HANDLERS:
        # Given up. The row stays, with its error, for someone to look at.
        job.done_at = now
        log.error("job %s (%s) failed for good:\n%s", job.id, job.kind, error)
        if job.kind in GIVE_UP:
            GIVE_UP[job.kind](db, dict(job.payload), error)
    else:
        job.run_at = now + backoff(job.attempts)
        log.warning("job %s (%s) failed, will retry", job.id, job.kind)
    db.commit()


def run_once(db: Session, limit: int = 20) -> int:
    """Claim and run what is due. Returns how many jobs ran."""
    ids = claim(db, limit)
    for job_id in ids:
        execute(db, job_id)
    return len(ids)


def main(argv: list[str] | None = None) -> None:
    import app.jobs  # noqa: F401  (registers the handlers)
    from app.db.session import SessionLocal

    if argv and "--list-handlers" in argv:
        print("\n".join(sorted(HANDLERS)))
        return

    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    log.info("worker started; handlers: %s", sorted(HANDLERS) or "none yet")
    while not stop.is_set():
        try:
            with SessionLocal() as db:
                queue_daily(db)
                ran = run_once(db)
        except Exception:
            # The database restarting must not kill the worker.
            log.exception("worker tick failed")
            ran = 0
        if not ran:
            stop.wait(settings.worker_poll_seconds)
    log.info("worker stopped")


if __name__ == "__main__":
    # `python -m app.worker` runs this file as __main__, a second copy of the
    # module: app/jobs.py registers its handlers on `app.worker`, not on this
    # one. Hand over to the real module so the loop sees them.
    import sys

    from app import worker

    worker.main(sys.argv[1:])
