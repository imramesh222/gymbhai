import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.time import today_in_nepal
from tests.conftest import GymFixture, make_member, sell, sign_in

TODAY = today_in_nepal()


def pay(client: TestClient, membership_id, amount: int, **extra):
    return client.post(
        "/api/v1/payments",
        json={
            "membership_id": str(membership_id),
            "amount": amount,
            "method": "cash",
            **extra,
        },
    )


def test_part_payments_reduce_dues(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a)
    membership, _ = sell(db, gym_a, member, paid=500_00)
    sign_in(db, client, gym_a.owner)

    assert pay(client, membership.id, 400_00).status_code == 201
    detail = client.get(f"/api/v1/members/{member.id}").json()
    assert detail["dues"] == 600_00
    assert [p["receipt_no"] for p in detail["payments"]] == [2, 1]


def test_more_than_owed_is_refused(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    membership, _ = sell(db, gym_a, make_member(db, gym_a), paid=1000_00)
    sign_in(db, client, gym_a.owner)
    response = pay(client, membership.id, 600_00)
    assert response.status_code == 422
    assert response.json() == {
        "detail": "That is more than is owed on this membership.",
        "code": "overpayment",
        "owed": 500_00,
    }


def test_a_transaction_id_pays_for_one_thing(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    first, _ = sell(db, gym_a, make_member(db, gym_a))
    second, _ = sell(db, gym_a, make_member(db, gym_a, phone="9800000001"))
    sign_in(db, client, gym_a.owner)
    assert pay(client, first.id, 100_00, transaction_ref="KH-1").status_code == 201
    response = pay(client, second.id, 100_00, transaction_ref=" KH-1 ")
    assert response.status_code == 409
    assert response.json()["code"] == "transaction_ref_used"


def test_voided_payments_count_for_nothing(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a)
    _, payment = sell(db, gym_a, member, paid=1500_00)
    sign_in(db, client, gym_a.owner)
    assert (
        client.post(
            f"/api/v1/payments/{payment.id}/void", json={"reason": "x"}
        ).status_code
        == 422
    )
    response = client.post(
        f"/api/v1/payments/{payment.id}/void", json={"reason": "entered twice"}
    )
    assert response.json()["void_reason"] == "entered twice"
    assert client.get(f"/api/v1/members/{member.id}").json()["dues"] == 1500_00
    again = client.post(f"/api/v1/payments/{payment.id}/void", json={"reason": "again"})
    assert again.status_code == 409


def test_editing_a_payment_is_logged(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    membership, payment = sell(db, gym_a, make_member(db, gym_a), paid=1000_00)
    sign_in(db, client, gym_a.owner)
    response = client.patch(
        f"/api/v1/payments/{payment.id}",
        json={"amount": 1200_00, "method": "fonepay", "reason": "typo"},
    )
    assert response.status_code == 200
    history = client.get(f"/api/v1/memberships/{membership.id}/history").json()
    edit = next(h for h in history if h["action"] == "payment.updated")
    assert edit["changes"]["amount"] == {"before": 1000_00, "after": 1200_00}
    assert edit["reason"] == "typo"


def test_payments_list_totals_for_the_till(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sell(db, gym_a, make_member(db, gym_a), paid=1500_00)
    _, voided = sell(db, gym_a, make_member(db, gym_a, phone="9800000002"), paid=700_00)
    sign_in(db, client, gym_a.owner)
    client.post(f"/api/v1/payments/{voided.id}/void", json={"reason": "mistake"})

    body = client.get(
        "/api/v1/payments",
        params={"date_from": TODAY.isoformat(), "date_to": TODAY.isoformat()},
    ).json()
    assert body["total"] == 2
    assert body["sum_amount"] == 1500_00
    assert body["by_method"] == {"cash": 1500_00}
    yesterday = (TODAY - dt.timedelta(days=1)).isoformat()
    assert (
        client.get("/api/v1/payments", params={"date_to": yesterday}).json()["total"]
        == 0
    )


def test_receipt(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    member = make_member(db, gym_a)
    _, payment = sell(db, gym_a, member, paid=1000_00)
    sign_in(db, client, gym_a.owner)
    receipt = client.get(f"/api/v1/payments/{payment.id}/receipt").json()
    assert receipt["gym_name"] == "Gym fitness-zone"
    assert receipt["member_code"] == member.member_code
    assert receipt["membership_total"] == 1500_00
    assert receipt["dues_after"] == 500_00
    assert receipt["date_display"] == "both"
