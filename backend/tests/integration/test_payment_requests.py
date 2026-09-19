import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.messaging import SmsMessage
from app.models.payment import GymPaymentMethod
from app.services import member_auth
from tests.conftest import GymFixture, make_member, priced_plan, sell, sign_in


@pytest.fixture
def setup(client: TestClient, db: Session, gym_a: GymFixture):
    member = make_member(db, gym_a)
    current, _ = sell(db, gym_a, member, paid=1500_00)
    plan = priced_plan(db, gym_a.gym)
    esewa = GymPaymentMethod(gym_id=gym_a.gym.id, kind="esewa", label="eSewa")
    db.add(esewa)
    db.commit()
    issued = member_auth.start_session(db, member, None)
    db.commit()
    app = TestClient(client.app)
    app.headers["Authorization"] = f"Bearer {issued.access_token}"
    sign_in(db, client, gym_a.owner)
    return member, current, plan, esewa, app


def ask(app: TestClient, plan, esewa, amount=1500_00, ref="ES-1"):
    return app.post(
        "/api/v1/m/payment-requests",
        json={
            "plan_id": str(plan.id),
            "payment_method_id": str(esewa.id),
            "amount": amount,
            "transaction_ref": ref,
        },
    )


def test_renew_from_the_app_and_approve(client: TestClient, db: Session, setup) -> None:
    member, current, plan, esewa, app = setup
    options = app.get("/api/v1/m/renew").json()
    assert [p["name"] for p in options["plans"]] == ["1 month"]
    assert (
        options["renewal_starts_on"]
        == (current.end_date + dt.timedelta(days=1)).isoformat()
    )
    assert options["payment_methods"][0]["label"] == "eSewa"

    created = ask(app, plan, esewa)
    assert created.status_code == 201, created.text
    assert client.get("/api/v1/payment-requests/count").json() == {"pending": 1}
    [waiting] = client.get("/api/v1/payment-requests").json()
    assert waiting["member_name"] == "Sita Rai"
    assert waiting["expected_total"] == 1500_00

    approved = client.post(f"/api/v1/payment-requests/{waiting['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["reviewed_by_name"] == "Owner of fitness-zone"

    detail = client.get(f"/api/v1/members/{member.id}").json()
    renewal = detail["memberships"][0]
    assert renewal["source"] == "app_request"
    assert (
        renewal["start_date"] == (current.end_date + dt.timedelta(days=1)).isoformat()
    )
    assert detail["payments"][0]["transaction_ref"] == "ES-1"
    assert detail["payments"][0]["method"] == "esewa"
    assert db.scalars(select(SmsMessage).where(SmsMessage.kind == "membership")).first()
    mine = app.get("/api/v1/m/me/payments").json()
    assert mine["requests"][0]["status"] == "approved"


def test_a_wrong_amount_needs_a_decision(client: TestClient, setup) -> None:
    _, _, plan, esewa, app = setup
    row = ask(app, plan, esewa, amount=1000_00).json()
    refused = client.post(f"/api/v1/payment-requests/{row['id']}/approve", json={})
    assert refused.status_code == 409
    assert refused.json()["code"] == "amount_mismatch"
    assert refused.json()["expected"] == 1500_00
    part = client.post(
        f"/api/v1/payment-requests/{row['id']}/approve",
        json={"accept_part_payment": True},
    )
    assert part.status_code == 200


def test_reject_tells_the_member_why(client: TestClient, db: Session, setup) -> None:
    _, _, plan, esewa, app = setup
    row = ask(app, plan, esewa).json()
    client.post(
        f"/api/v1/payment-requests/{row['id']}/reject",
        json={"reason": "amount not received"},
    )
    mine = app.get("/api/v1/m/me/payments").json()["requests"][0]
    assert (
        mine["status"] == "rejected" and mine["reject_reason"] == "amount not received"
    )
    sms = db.scalars(select(SmsMessage).where(SmsMessage.kind == "payment")).one()
    assert "amount not received" in sms.body


def test_one_transaction_id_once(
    client: TestClient, db: Session, gym_a: GymFixture, setup
) -> None:
    member, current, plan, esewa, app = setup
    first = ask(app, plan, esewa, ref="ES-9").json()
    # A second request while one is pending is refused anyway.
    assert ask(app, plan, esewa, ref="ES-10").json()["code"] == "request_pending"
    app.post(f"/api/v1/m/payment-requests/{first['id']}/withdraw")
    # A desk payment for someone else already used ES-11.
    other, _ = sell(db, gym_a, make_member(db, gym_a, phone="9800000055"))
    client.post(
        "/api/v1/payments",
        json={
            "membership_id": str(other.id),
            "amount": 1,
            "method": "esewa",
            "transaction_ref": "ES-11",
        },
    )
    reused = ask(app, plan, esewa, ref="ES-11")
    assert reused.status_code == 409 and reused.json()["code"] == "transaction_ref_used"


def test_withdraw_only_while_pending(client: TestClient, setup) -> None:
    _, _, plan, esewa, app = setup
    row = ask(app, plan, esewa).json()
    client.post(
        f"/api/v1/payment-requests/{row['id']}/reject", json={"reason": "not received"}
    )
    response = app.post(f"/api/v1/m/payment-requests/{row['id']}/withdraw")
    assert response.json()["code"] == "request_closed"


def test_screenshot(client: TestClient, setup, tmp_path, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "media_root", str(tmp_path))
    _, _, plan, esewa, app = setup
    row = ask(app, plan, esewa, ref=None).json()
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 64
    uploaded = app.post(
        f"/api/v1/m/payment-requests/{row['id']}/screenshot",
        files={"file": ("s.png", png, "image/png")},
    ).json()
    assert uploaded["screenshot_url"]
    [waiting] = client.get("/api/v1/payment-requests").json()
    assert client.get(waiting["screenshot_url"]).content == png
