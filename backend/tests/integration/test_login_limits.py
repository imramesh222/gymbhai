"""Limits on guessing staff passwords (PLAN.md §16.1, step 6.1)."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utcnow
from app.jobs import cleanup
from app.models.activity import ActivityLog
from app.models.staff import LoginAttempt
from tests.conftest import TEST_PASSWORD, GymFixture

WRONG = "not-the-password"


def login(client: TestClient, identifier: str, password: str = TEST_PASSWORD):
    return client.post(
        "/api/v1/auth/login", json={"identifier": identifier, "password": password}
    )


def fail(client: TestClient, identifier: str, times: int) -> None:
    for _ in range(times):
        assert login(client, identifier, WRONG).status_code == 401


def attempts(db: Session, identifier: str) -> int:
    return db.scalar(
        select(func.count())
        .select_from(LoginAttempt)
        .where(LoginAttempt.identifier == identifier)
    )


def test_five_wrong_tries_lock_the_account(
    client: TestClient, gym_a: GymFixture
) -> None:
    fail(client, "a@example.com", 5)

    # Even the right password is refused until the wait is over.
    locked = login(client, "a@example.com")
    assert locked.status_code == 429
    assert locked.json()["code"] == "too_many_attempts"
    wait = int(locked.headers["Retry-After"])
    assert 0 < wait <= settings.login_window_minutes * 60


def test_unknown_accounts_lock_the_same_way(
    client: TestClient, gym_a: GymFixture
) -> None:
    fail(client, "a@example.com", 5)
    fail(client, "nobody@example.com", 5)
    real = login(client, "a@example.com")
    unknown = login(client, "nobody@example.com")
    assert real.status_code == unknown.status_code == 429
    assert real.json() == unknown.json()


def test_every_way_of_typing_a_phone_shares_one_count(
    client: TestClient, gym_a: GymFixture
) -> None:
    fail(client, "9841000001", 3)
    fail(client, "+977-984-1000001", 2)
    assert login(client, "984 1000001").status_code == 429


def test_a_success_starts_the_count_again(
    client: TestClient, gym_a: GymFixture
) -> None:
    fail(client, "a@example.com", 4)
    assert login(client, "a@example.com").status_code == 200
    fail(client, "a@example.com", 4)
    assert login(client, "a@example.com").status_code == 200


def test_the_lock_lifts_when_the_window_has_passed(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    fail(client, "a@example.com", 5)
    assert login(client, "a@example.com").status_code == 429

    window = dt.timedelta(minutes=settings.login_window_minutes, seconds=1)
    db.execute(update(LoginAttempt).values(at=LoginAttempt.at - window))
    db.commit()
    assert login(client, "a@example.com").status_code == 200


def test_tries_refused_by_the_limit_are_not_counted(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    """Otherwise someone knocking every minute would keep the owner locked out."""
    fail(client, "a@example.com", 5)
    for _ in range(3):
        assert login(client, "a@example.com", WRONG).status_code == 429
    assert attempts(db, "a@example.com") == 5


def test_one_address_is_limited_across_accounts(
    client: TestClient, gym_a: GymFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "login_max_failures_per_ip", 3)
    for n in range(3):
        fail(client, f"guess{n}@example.com", 1)

    # A different account, the right password, the same address: refused.
    response = login(client, "a@example.com")
    assert response.status_code == 429
    assert response.json()["code"] == "too_many_attempts"


def test_the_lockout_is_in_the_gym_activity_log(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    fail(client, "a@example.com", 5)
    entry = db.scalars(
        select(ActivityLog).where(ActivityLog.action == "staff.locked_out")
    ).one()
    assert entry.gym_id == gym_a.gym.id
    assert entry.entity_id == gym_a.owner.id
    assert entry.ip == "testclient"


def test_cleanup_removes_old_tries(db: Session) -> None:
    db.add_all(
        [
            LoginAttempt(
                identifier="old@example.com",
                succeeded=False,
                at=utcnow() - dt.timedelta(days=2),
            ),
            LoginAttempt(identifier="new@example.com", succeeded=False, at=utcnow()),
        ]
    )
    db.commit()
    cleanup(db, {})
    assert attempts(db, "old@example.com") == 0
    assert attempts(db, "new@example.com") == 1
