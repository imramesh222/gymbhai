import datetime as dt
from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app import worker
from app.core.time import utcnow


@pytest.fixture
def handlers() -> Generator[dict[str, list[dict[str, Any]]]]:
    """Two throwaway handlers: one that records its payloads, one that fails."""
    seen: dict[str, list[dict[str, Any]]] = {"ok": [], "boom": []}

    def ok(db: Session, payload: dict[str, Any]) -> None:
        seen["ok"].append(payload)

    def boom(db: Session, payload: dict[str, Any]) -> None:
        seen["boom"].append(payload)
        raise RuntimeError("gateway down")

    worker.HANDLERS.update({"test.ok": ok, "test.boom": boom})
    yield seen
    worker.HANDLERS.pop("test.ok")
    worker.HANDLERS.pop("test.boom")


def test_a_due_job_runs_once(db: Session, handlers) -> None:
    job = worker.enqueue(db, "test.ok", {"n": 1})
    db.commit()

    assert worker.run_once(db) == 1
    assert handlers["ok"] == [{"n": 1}]
    db.refresh(job)
    assert job.done_at is not None and job.error is None

    assert worker.run_once(db) == 0
    assert handlers["ok"] == [{"n": 1}]


def test_a_future_job_waits(db: Session, handlers) -> None:
    worker.enqueue(db, "test.ok", run_at=utcnow() + dt.timedelta(hours=1))
    db.commit()
    assert worker.run_once(db) == 0


def test_a_failing_job_backs_off_then_gives_up(db: Session, handlers) -> None:
    job = worker.enqueue(db, "test.boom")
    db.commit()

    for attempt in range(1, worker.MAX_ATTEMPTS + 1):
        job.run_at = utcnow() - dt.timedelta(seconds=1)
        db.commit()
        assert worker.run_once(db) == 1
        db.refresh(job)
        assert job.attempts == attempt
        assert "gateway down" in job.error

        if attempt < worker.MAX_ATTEMPTS:
            assert job.done_at is None
            assert job.run_at > utcnow()
        else:
            assert job.done_at is not None

    assert len(handlers["boom"]) == worker.MAX_ATTEMPTS


def test_unknown_kind_fails_at_once(db: Session) -> None:
    job = worker.enqueue(db, "test.nobody-handles-this")
    db.commit()
    worker.run_once(db)
    db.refresh(job)
    assert job.done_at is not None and "No handler" in job.error


def test_a_job_locked_by_a_live_worker_is_not_taken(db: Session, handlers) -> None:
    job = worker.enqueue(db, "test.ok")
    job.locked_at = utcnow()
    db.commit()
    assert worker.run_once(db) == 0


def test_a_job_locked_by_a_dead_worker_is_taken(db: Session, handlers) -> None:
    job = worker.enqueue(db, "test.ok")
    job.locked_at = utcnow() - worker.LOCK_TIMEOUT - dt.timedelta(seconds=1)
    db.commit()
    assert worker.run_once(db) == 1


def test_backoff_grows() -> None:
    assert [worker.backoff(n).total_seconds() / 60 for n in (1, 2, 3)] == [1, 5, 25]
