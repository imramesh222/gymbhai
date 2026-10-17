"""Saving a payment once, however many times it is sent (PLAN.md §16.1, 6.5)."""

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.membership import Membership
from app.models.payment import Payment
from app.models.platform import SubscriptionPayment
from tests.conftest import GymFixture, make_member, priced_plan, sell, sign_in

KEY = "sale-0001-abcdef"


def count(db: Session, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def twice(client: TestClient, url: str, body: dict, key: str = KEY):
    headers = {"Idempotency-Key": key}
    return (
        client.post(url, json=body, headers=headers),
        client.post(url, json=body, headers=headers),
    )


def test_a_sale_sent_twice_is_saved_once(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    plan = priced_plan(db, gym_a.gym)
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    sale = {"plan_id": str(plan.id), "payment": {"amount": 1500_00, "method": "cash"}}
    first, again = twice(client, f"/api/v1/members/{member.id}/memberships", sale)

    assert first.status_code == again.status_code == 201
    assert again.json() == first.json()
    assert again.headers["Idempotent-Replayed"] == "true"
    assert "Idempotent-Replayed" not in first.headers
    assert count(db, Membership) == 1
    assert count(db, Payment) == 1


def test_a_new_member_sent_twice_is_added_once(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    plan = priced_plan(db, gym_a.gym)
    sign_in(db, client, gym_a.owner)
    body = {
        "name": "Sita Rai",
        "phone": "9812345678",
        "membership": {
            "plan_id": str(plan.id),
            "payment": {"amount": 1500_00, "method": "cash"},
        },
    }
    first, again = twice(client, "/api/v1/members", body)
    assert first.status_code == again.status_code == 201
    assert again.json()["member"]["id"] == first.json()["member"]["id"]
    assert count(db, Payment) == 1


def test_a_payment_sent_twice_is_recorded_once(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    membership, _ = sell(db, gym_a, make_member(db, gym_a))
    sign_in(db, client, gym_a.owner)
    body = {"membership_id": str(membership.id), "amount": 500_00, "method": "cash"}
    first, again = twice(client, "/api/v1/payments", body)
    assert first.status_code == again.status_code == 201
    assert again.json()["id"] == first.json()["id"]
    assert count(db, Payment) == 1


def test_a_refund_sent_twice_is_recorded_once(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    membership, _ = sell(db, gym_a, make_member(db, gym_a), paid=1500_00)
    sign_in(db, client, gym_a.owner)
    body = {"membership_id": str(membership.id), "amount": 500_00, "method": "cash"}
    first, again = twice(client, "/api/v1/payments/refunds", body)
    assert first.status_code == again.status_code == 201
    assert count(db, Payment) == 2  # the sale's payment and one refund


def test_paying_us_sent_twice_is_sent_once(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    body = {
        "kind": "sms",
        "sms_credits": 500,
        "amount": 500_00,
        "transaction_ref": "ESW-123456",
    }
    first, again = twice(client, "/api/v1/subscription/payments", body)
    assert first.status_code == again.status_code == 201
    assert count(db, SubscriptionPayment) == 1


def test_two_payments_with_their_own_keys_are_two_payments(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    membership, _ = sell(db, gym_a, make_member(db, gym_a))
    sign_in(db, client, gym_a.owner)
    body = {"membership_id": str(membership.id), "amount": 500_00, "method": "cash"}
    client.post("/api/v1/payments", json=body, headers={"Idempotency-Key": "pay-one-1"})
    client.post("/api/v1/payments", json=body, headers={"Idempotency-Key": "pay-two-2"})
    assert count(db, Payment) == 2


def test_a_key_reused_for_something_else_is_refused(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    membership, _ = sell(db, gym_a, make_member(db, gym_a))
    sign_in(db, client, gym_a.owner)
    url, headers = "/api/v1/payments", {"Idempotency-Key": KEY}
    body = {"membership_id": str(membership.id), "amount": 500_00, "method": "cash"}
    client.post(url, json=body, headers=headers)
    other = client.post(url, json={**body, "amount": 400_00}, headers=headers)
    assert other.status_code == 409
    assert other.json()["code"] == "idempotency_key_reused"


def test_a_failed_request_keeps_nothing(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    """Its transaction rolled back, key and all: trying again runs it again."""
    membership, _ = sell(db, gym_a, make_member(db, gym_a))  # Rs 1,500 owed
    sign_in(db, client, gym_a.owner)
    url, headers = "/api/v1/payments", {"Idempotency-Key": KEY}
    too_much = {
        "membership_id": str(membership.id),
        "amount": 9999_00,
        "method": "cash",
    }
    refused = client.post(url, json=too_much, headers=headers)
    assert refused.json()["code"] == "overpayment"
    right = {**too_much, "amount": 500_00}
    assert client.post(url, json=right, headers=headers).status_code == 201


def test_another_gym_never_gets_this_gyms_answer(
    client: TestClient, db: Session, gym_a: GymFixture, gym_b: GymFixture
) -> None:
    a_membership, _ = sell(db, gym_a, make_member(db, gym_a))
    b_membership, _ = sell(db, gym_b, make_member(db, gym_b, phone="9819999999"))
    headers = {"Idempotency-Key": KEY}
    sign_in(db, client, gym_a.owner)
    body = {"membership_id": str(a_membership.id), "amount": 500_00, "method": "cash"}
    a_answer = client.post("/api/v1/payments", json=body, headers=headers)
    sign_in(db, client, gym_b.owner)
    body = {"membership_id": str(b_membership.id), "amount": 500_00, "method": "cash"}
    b_answer = client.post("/api/v1/payments", json=body, headers=headers)
    assert b_answer.status_code == 201
    assert "Idempotent-Replayed" not in b_answer.headers
    assert b_answer.json()["id"] != a_answer.json()["id"]


def test_a_malformed_key_is_refused(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    membership, _ = sell(db, gym_a, make_member(db, gym_a))
    sign_in(db, client, gym_a.owner)
    body = {"membership_id": str(membership.id), "amount": 500_00, "method": "cash"}
    response = client.post(
        "/api/v1/payments", json=body, headers={"Idempotency-Key": "bad key!"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "bad_idempotency_key"


def test_without_a_key_nothing_changes(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    membership, _ = sell(db, gym_a, make_member(db, gym_a))
    sign_in(db, client, gym_a.owner)
    body = {"membership_id": str(membership.id), "amount": 500_00, "method": "cash"}
    client.post("/api/v1/payments", json=body)
    client.post("/api/v1/payments", json=body)
    assert count(db, Payment) == 2
