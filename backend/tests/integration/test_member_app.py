import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import today_in_nepal
from app.models.member_app import OtpCode
from app.models.messaging import SmsMessage
from app.services import member_auth
from tests.conftest import GymFixture, make_member, sell, sign_in

CODE = "123456"
SLUG = "fitness-zone"


@pytest.fixture(autouse=True)
def fixed_code(monkeypatch):
    monkeypatch.setattr(member_auth.secrets, "randbelow", lambda n: int(CODE))


def ask(client: TestClient, **who):
    return client.post(f"/api/v1/m/{SLUG}/otp/request", json=who)


def verify(client: TestClient, code: str = CODE, **who):
    return client.post(f"/api/v1/m/{SLUG}/otp/verify", json={"code": code, **who})


def signed_in(client: TestClient, phone: str) -> dict:
    assert ask(client, phone=phone).status_code == 200
    body = verify(client, phone=phone).json()
    client.headers["Authorization"] = f"Bearer {body['access_token']}"
    return body


def test_sign_in_by_sms_code(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a, phone="9812345678")
    sell(db, gym_a, member, paid=1500_00)

    requested = ask(client, phone="+977 981-2345678")
    assert requested.status_code == 200
    assert requested.json() == {
        "channel": "sms",
        "sent_to": "981xxxx678",
        "expires_in": 300,
    }
    otp_sms = db.scalars(select(SmsMessage).where(SmsMessage.kind == "otp")).one()
    assert otp_sms.status == "sent"
    # Never left readable in the SMS log.
    assert CODE not in otp_sms.body

    body = verify(client, phone="9812345678").json()
    assert body["me"]["name"] == "Sita Rai"
    assert body["me"]["state"]["status"] == "active"
    assert body["me"]["qr"]["member_hex"] == member.id.hex
    assert "gb_member_refresh" in client.cookies

    client.headers["Authorization"] = f"Bearer {body['access_token']}"
    assert client.get("/api/v1/m/me").json()["member_code"] == member.member_code


def test_a_code_works_once(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    make_member(db, gym_a)
    ask(client, phone="9812345678")
    assert verify(client, phone="9812345678").status_code == 200
    assert verify(client, phone="9812345678").status_code == 401


def test_wrong_codes_run_out(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    make_member(db, gym_a)
    ask(client, phone="9812345678")
    for _ in range(5):
        assert verify(client, code="000000", phone="9812345678").status_code == 401
    # Even the right one is refused now.
    assert verify(client, phone="9812345678").status_code == 401


def test_an_expired_code(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    make_member(db, gym_a)
    ask(client, phone="9812345678")
    row = db.scalars(select(OtpCode)).one()
    row.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    db.commit()
    assert verify(client, phone="9812345678").status_code == 401


def test_three_codes_per_quarter_hour(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    make_member(db, gym_a)
    for _ in range(3):
        assert ask(client, phone="9812345678").status_code == 200
    response = ask(client, phone="9812345678")
    assert response.status_code == 429
    assert response.json()["code"] == "too_many_codes"


def test_guessing_numbers_is_rate_limited_too(
    client: TestClient, db: Session, gym_a: GymFixture, monkeypatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "otp_per_ip", 3)
    for n in range(3):
        assert ask(client, phone=f"981000000{n}").status_code == 404
    assert ask(client, phone="9810000009").status_code == 429


def test_sign_in_codes_are_free_for_the_gym(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    from app.services.sms import service as sms

    make_member(db, gym_a)
    sms.add_credits(db, gym_a.gym.id, -50, "test")
    assert ask(client, phone="9812345678").status_code == 200


def test_turned_off_access_looks_unregistered(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a)
    member.app_access = False
    db.commit()
    assert ask(client, phone="9812345678").json()["code"] == "not_registered"


def test_a_shared_phone_asks_who_you_are(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    parent = make_member(db, gym_a, name="Parent Rai")
    child = make_member(db, gym_a, name="Child Rai")
    ask(client, phone="9812345678")
    choice = verify(client, phone="9812345678").json()
    assert choice["access_token"] is None
    assert {c["name"] for c in choice["choose"]} == {"Parent Rai", "Child Rai"}

    body = verify(client, phone="9812345678", member_id=str(child.id)).json()
    assert body["me"]["id"] == str(child.id)
    assert parent.id != child.id


def test_sign_in_by_email(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    member = make_member(db, gym_a)
    member.email = "sita@example.com"
    db.commit()
    assert ask(client, email="Sita@Example.com").json()["channel"] == "email"
    assert verify(client, email="sita@example.com").status_code == 200


def test_expired_members_can_still_sign_in(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a)
    today = today_in_nepal()
    sell(
        db,
        gym_a,
        member,
        start_date=today - dt.timedelta(days=40),
        end_date=today - dt.timedelta(days=10),
    )
    body = signed_in(client, "9812345678")
    assert body["me"]["state"]["status"] == "expired"


def test_refresh_and_sign_out(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    make_member(db, gym_a)
    signed_in(client, "9812345678")
    assert client.post("/api/v1/m/auth/refresh").status_code == 200
    assert client.post("/api/v1/m/auth/logout").status_code == 204
    assert client.post("/api/v1/m/auth/refresh").status_code == 401


def test_staff_controls_sign_members_out_at_once(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a)
    staff_client = TestClient(client.app)
    for action in ("access", "phone", "sign-out-all", "qr"):
        # A session straight away: four codes in a row would hit the limit.
        issued = member_auth.start_session(db, member, None)
        db.commit()
        client.headers["Authorization"] = f"Bearer {issued.access_token}"
        assert client.get("/api/v1/m/me").status_code == 200
        sign_in(db, staff_client, gym_a.owner)
        if action == "access":
            staff_client.patch(
                f"/api/v1/members/{member.id}/access", json={"app_access": False}
            )
        elif action == "phone":
            staff_client.patch(
                f"/api/v1/members/{member.id}", json={"phone": "9812345679"}
            )
        elif action == "sign-out-all":
            staff_client.post(f"/api/v1/members/{member.id}/sign-out-all")
        else:
            staff_client.post(f"/api/v1/members/{member.id}/qr/reissue")
        assert client.get("/api/v1/m/me").status_code == 401, action
        # Put things back for the next round.
        db.refresh(member)
        member.app_access = True
        member.phone = "9812345678"
        db.commit()


def test_notices_reach_the_app(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a)
    staff_client = TestClient(client.app)
    sign_in(db, staff_client, gym_a.owner)
    staff_client.post(
        "/api/v1/notices", json={"title": "Closed Saturday", "body": "Tihar"}
    )
    signed_in(client, member.phone)
    assert client.get("/api/v1/m/notices").json()[0]["title"] == "Closed Saturday"
    assert (
        client.get("/api/v1/m/me").json()["latest_notice"]["title"] == "Closed Saturday"
    )


def test_public_gym_page(client: TestClient, gym_a: GymFixture) -> None:
    body = client.get(f"/api/v1/m/{SLUG}/gym").json()
    assert body["name"] == "Gym fitness-zone"
    assert body["date_display"] == "both"
    assert client.get("/api/v1/m/no-such-gym/gym").status_code == 404
