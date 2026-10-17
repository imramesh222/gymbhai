"""Members' actions from the phone app: sent twice, done once (PLAN.md §17.4)."""

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import today_in_nepal
from app.models.lead import Lead
from app.models.member_app import FreezeRequest, PaymentRequest
from app.models.payment import GymPaymentMethod
from app.services import member_auth
from tests.conftest import GymFixture, make_member, priced_plan, sell, sign_in

TODAY = today_in_nepal()


def app_for(client: TestClient, db: Session, member) -> TestClient:
    issued = member_auth.start_session(db, member, None, "app")
    db.commit()
    app = TestClient(client.app)
    app.headers["Authorization"] = f"Bearer {issued.access_token}"
    return app


def test_ive_paid_twice_is_one_request(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a)
    plan = priced_plan(db, gym_a.gym)
    esewa = GymPaymentMethod(gym_id=gym_a.gym.id, kind="esewa", label="eSewa")
    db.add(esewa)
    db.commit()
    app = app_for(client, db, member)
    body = {
        "plan_id": str(plan.id),
        "payment_method_id": str(esewa.id),
        "amount": 1500_00,
        "transaction_ref": "ES-TWICE",
    }
    key = {"Idempotency-Key": "renew-key-0001"}
    first = app.post("/api/v1/m/payment-requests", json=body, headers=key)
    again = app.post("/api/v1/m/payment-requests", json=body, headers=key)
    assert first.status_code == again.status_code == 201
    assert again.headers["Idempotent-Replayed"] == "true"
    assert first.json()["id"] == again.json()["id"]
    assert len(db.scalars(select(PaymentRequest)).all()) == 1

    # Withdrawing twice: the same answer, not "already dealt with".
    url = f"/api/v1/m/payment-requests/{first.json()['id']}/withdraw"
    out = {"Idempotency-Key": "withdraw-key-01"}
    assert app.post(url, headers=out).json()["status"] == "withdrawn"
    assert app.post(url, headers=out).status_code == 200


def test_a_key_is_only_ever_its_own_members(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    mine = make_member(db, gym_a, phone="9800000991")
    theirs = make_member(db, gym_a, phone="9800000992", name="Hari")
    for m in (mine, theirs):
        sell(db, gym_a, m, start_date=TODAY, end_date=TODAY + dt.timedelta(days=29))
    body = {
        "from_date": str(TODAY + dt.timedelta(days=2)),
        "to_date": str(TODAY + dt.timedelta(days=5)),
        "reason": "Away",
    }
    key = {"Idempotency-Key": "freeze-key-0001"}
    first = app_for(client, db, mine).post(
        "/api/v1/m/freeze-requests", json=body, headers=key
    )
    assert first.status_code == 201
    # Another member with the same key gets nobody's answer.
    other = app_for(client, db, theirs).post(
        "/api/v1/m/freeze-requests", json=body, headers=key
    )
    assert other.status_code == 409
    assert other.json()["code"] == "idempotency_key_reused"
    assert len(db.scalars(select(FreezeRequest)).all()) == 1
    # Staff can't use it either.
    sign_in(db, client, gym_a.owner)
    member = make_member(db, gym_a, phone="9800000993", name="Desk")
    desk = client.post(
        f"/api/v1/members/{member.id}/memberships",
        json={"plan_id": str(priced_plan(db, gym_a.gym).id)},
        headers=key,
    )
    assert desk.status_code == 409


def test_join_form_twice(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    sign_in(db, client, gym_a.owner)
    client.patch("/api/v1/gym", json={"settings": {"join_form": True}})
    client.headers.pop("Authorization", None)
    body = {"name": "Maya", "phone": "9800000994"}
    key = {"Idempotency-Key": "join-key-000001"}
    url = f"/api/v1/m/{gym_a.gym.slug}/join"
    assert client.post(url, json=body, headers=key).status_code == 202
    assert client.post(url, json=body, headers=key).status_code == 202
    assert len(db.scalars(select(Lead)).all()) == 1


def test_app_sessions_keep_their_token_in_the_body(
    client: TestClient, db: Session, gym_a: GymFixture, monkeypatch
) -> None:
    monkeypatch.setattr(member_auth.secrets, "randbelow", lambda n: 123456)
    member = make_member(db, gym_a)
    slug = gym_a.gym.slug
    client.post(f"/api/v1/m/{slug}/otp/request", json={"phone": member.phone})
    signed = client.post(
        f"/api/v1/m/{slug}/otp/verify",
        json={"phone": member.phone, "code": "123456", "client": "app"},
    )
    assert "gb_member_refresh" not in signed.cookies
    first = signed.json()["refresh_token"]
    assert first and signed.json()["access_token"]

    renewed = client.post("/api/v1/m/auth/refresh", json={"refresh_token": first})
    second = renewed.json()["refresh_token"]
    assert second and second != first
    # The answer was lost on the way: the old token again, still within the
    # grace, gets a token rather than a signed-out app.
    retried = client.post("/api/v1/m/auth/refresh", json={"refresh_token": first})
    assert retried.status_code == 200 and retried.json()["refresh_token"]

    latest = retried.json()["refresh_token"]
    assert (
        client.post("/api/v1/m/auth/logout", json={"refresh_token": latest}).status_code
        == 204
    )
    gone = client.post("/api/v1/m/auth/refresh", json={"refresh_token": latest})
    assert gone.status_code == 401

    # The web keeps its cookie and never sees the token.
    client.post(f"/api/v1/m/{slug}/otp/request", json={"phone": member.phone})
    web = client.post(
        f"/api/v1/m/{slug}/otp/verify", json={"phone": member.phone, "code": "123456"}
    )
    assert web.json()["refresh_token"] is None
    assert "gb_member_refresh" in web.cookies
