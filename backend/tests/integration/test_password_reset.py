"""Forgot password (PLAN.md §16.1, step 6.2)."""

import datetime as dt
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utcnow
from app.models.activity import ActivityLog
from app.models.messaging import SmsMessage
from app.models.staff import StaffPasswordReset, StaffSession, StaffUser
from app.services import email
from tests.conftest import TEST_PASSWORD, GymFixture, sign_in

CODE = "246810"
NEW_PASSWORD = "a-brand-new-password"


@pytest.fixture(autouse=True)
def known_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "otp_test_code", CODE)


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        email, "send", lambda to, subject, body: sent.append((to, body))
    )
    return sent


def ask(client: TestClient, identifier: str):
    return client.post("/api/v1/auth/password-reset", json={"identifier": identifier})


def confirm(
    client: TestClient, identifier: str, code: str = CODE, password: str = NEW_PASSWORD
):
    return client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"identifier": identifier, "code": code, "new_password": password},
    )


def login(client: TestClient, identifier: str, password: str):
    return client.post(
        "/api/v1/auth/login", json={"identifier": identifier, "password": password}
    )


def test_reset_by_email(
    client: TestClient, gym_a: GymFixture, outbox: list[tuple[str, str]]
) -> None:
    assert ask(client, "A@Example.com").status_code == 202
    assert [to for to, _ in outbox] == ["a@example.com"]
    assert CODE in outbox[0][1]

    assert confirm(client, "a@example.com").status_code == 204
    assert login(client, "a@example.com", TEST_PASSWORD).status_code == 401
    assert login(client, "a@example.com", NEW_PASSWORD).status_code == 200


def test_reset_by_sms_hides_the_code_from_the_sms_log(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    assert ask(client, "9841000001").status_code == 202
    message = db.scalars(
        select(SmsMessage).where(SmsMessage.gym_id == gym_a.gym.id)
    ).one()
    assert message.to == "9841000001"
    assert message.status == "sent"
    # Staff can read the SMS log; the owner's code must not be in it.
    assert CODE not in message.body

    assert confirm(client, "+977 9841000001").status_code == 204
    assert login(client, "9841000001", NEW_PASSWORD).status_code == 200


def test_unknown_and_disabled_accounts_get_the_same_answer(
    client: TestClient,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
    outbox: list[tuple[str, str]],
) -> None:
    disabled = make_staff(gym_a.gym, is_active=False)
    real = ask(client, "a@example.com")
    unknown = ask(client, "nobody@example.com")
    off = ask(client, disabled.phone)
    assert real.status_code == unknown.status_code == off.status_code == 202
    assert real.json() == unknown.json() == off.json()
    assert [to for to, _ in outbox] == ["a@example.com"]

    assert confirm(client, "nobody@example.com").status_code == 401
    assert confirm(client, disabled.phone).status_code == 401


def test_every_device_is_signed_out(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    ask(client, "a@example.com")
    assert confirm(client, "a@example.com").status_code == 204
    live = db.scalars(
        select(StaffSession).where(
            StaffSession.staff_user_id == gym_a.owner.id,
            StaffSession.revoked_at.is_(None),
        )
    ).all()
    assert live == []


def test_a_code_works_once(client: TestClient, gym_a: GymFixture) -> None:
    ask(client, "a@example.com")
    assert confirm(client, "a@example.com").status_code == 204
    again = confirm(client, "a@example.com", password="yet-another-password")
    assert again.status_code == 401
    assert again.json()["code"] == "bad_code"


def test_five_wrong_codes_end_it(client: TestClient, gym_a: GymFixture) -> None:
    ask(client, "a@example.com")
    for _ in range(settings.otp_max_attempts):
        assert confirm(client, "a@example.com", code="000000").status_code == 401
    assert confirm(client, "a@example.com").status_code == 401


def test_an_expired_code_is_refused(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    ask(client, "a@example.com")
    db.execute(
        update(StaffPasswordReset).values(expires_at=utcnow() - dt.timedelta(seconds=1))
    )
    db.commit()
    assert confirm(client, "a@example.com").status_code == 401


def test_asking_is_limited(client: TestClient, gym_a: GymFixture) -> None:
    for _ in range(settings.otp_per_destination):
        assert ask(client, "nobody@example.com").status_code == 202
    limited = ask(client, "nobody@example.com")
    assert limited.status_code == 429
    assert limited.json()["code"] == "too_many_codes"


def test_obvious_passwords_are_refused(client: TestClient, gym_a: GymFixture) -> None:
    ask(client, "a@example.com")
    assert confirm(client, "a@example.com", password="password1").status_code == 422


def test_a_reset_opens_a_locked_account(client: TestClient, gym_a: GymFixture) -> None:
    for _ in range(settings.login_max_failures):
        login(client, "a@example.com", "not-the-password")
    assert login(client, "a@example.com", TEST_PASSWORD).status_code == 429

    ask(client, "a@example.com")
    assert confirm(client, "a@example.com").status_code == 204
    assert login(client, "a@example.com", NEW_PASSWORD).status_code == 200


def test_a_platform_admin_resets_by_email(
    client: TestClient, platform_admin: StaffUser, outbox: list[tuple[str, str]]
) -> None:
    ask(client, "admin@gymbhai.com")
    assert [to for to, _ in outbox] == ["admin@gymbhai.com"]
    assert confirm(client, "admin@gymbhai.com").status_code == 204


def test_the_reset_is_logged(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    ask(client, "a@example.com")
    confirm(client, "a@example.com")
    entry = db.scalars(
        select(ActivityLog).where(ActivityLog.action == "staff.password_reset_by_code")
    ).one()
    assert entry.gym_id == gym_a.gym.id
    assert entry.actor_id == gym_a.owner.id


def test_the_master_sign_in_code_never_resets_a_password(
    client: TestClient, gym_a: GymFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It is for members only: here it would hand over the owner's account."""
    monkeypatch.setattr(settings, "otp_test_code", None)
    monkeypatch.setattr(settings, "master_otp", "583920")
    ask(client, "9841000001")
    assert confirm(client, "9841000001", code="583920").status_code == 401
