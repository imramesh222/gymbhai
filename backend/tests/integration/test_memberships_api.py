import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.time import today_in_nepal
from app.models.gym import Branch
from tests.conftest import GymFixture, make_member, priced_plan, sell, sign_in

TODAY = today_in_nepal()


def test_edit_dates_and_price_with_history(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    membership, _ = sell(db, gym_a, make_member(db, gym_a))
    sign_in(db, client, gym_a.owner)
    new_end = (membership.end_date + dt.timedelta(days=5)).isoformat()
    response = client.patch(
        f"/api/v1/memberships/{membership.id}",
        json={"end_date": new_end, "discount": 200_00, "reason": "promised extra days"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["end_date"] == new_end
    assert response.json()["dues"] == 1300_00

    [latest, created] = client.get(
        f"/api/v1/memberships/{membership.id}/history"
    ).json()
    assert created["action"] == "membership.created"
    assert latest["action"] == "membership.updated"
    assert latest["reason"] == "promised extra days"
    assert latest["changes"]["discount"] == {"before": 0, "after": 200_00}


def test_upgrading_the_plan_recalculates(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a)
    membership, _ = sell(db, gym_a, member, paid=1500_00)
    one_month_end = membership.end_date
    three = priced_plan(db, gym_a.gym, months=3, price=4000_00)
    sign_in(db, client, gym_a.owner)
    response = client.patch(
        f"/api/v1/memberships/{membership.id}", json={"plan_id": str(three.id)}
    )
    body = response.json()
    assert body["plan_name"] == "3 months"
    assert body["price"] == 4000_00
    assert body["dues"] == 2500_00
    assert dt.date.fromisoformat(body["end_date"]) > one_month_end + dt.timedelta(
        days=50
    )


def test_extend_needs_a_reason(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    membership, _ = sell(db, gym_a, make_member(db, gym_a))
    end = membership.end_date
    sign_in(db, client, gym_a.owner)
    url = f"/api/v1/memberships/{membership.id}/extend"
    assert client.post(url, json={"days": 10}).status_code == 422
    response = client.post(url, json={"days": 10, "reason": "injury"})
    assert response.json()["end_date"] == (end + dt.timedelta(days=10)).isoformat()


def test_extend_everyone_for_dashain(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    koteshwor = Branch(gym_id=gym_a.gym.id, name="Koteshwor")
    db.add(koteshwor)
    db.commit()
    here, _ = sell(db, gym_a, make_member(db, gym_a))
    there, _ = sell(
        db, gym_a, make_member(db, gym_a, phone="9800000003"), branch_id=koteshwor.id
    )
    old, _ = sell(
        db,
        gym_a,
        make_member(db, gym_a, phone="9800000004"),
        start_date=TODAY - dt.timedelta(days=60),
        end_date=TODAY - dt.timedelta(days=30),
    )
    ends = {m.id: m.end_date for m in (here, there, old)}
    sign_in(db, client, gym_a.owner)

    response = client.post(
        "/api/v1/memberships/extend-all",
        json={
            "days": 7,
            "reason": "Closed for Dashain",
            "branch_id": str(gym_a.branch.id),
        },
    )
    assert response.json() == {"extended": 1}
    response = client.post(
        "/api/v1/memberships/extend-all", json={"days": 2, "reason": "Power cut"}
    )
    assert response.json() == {"extended": 2}
    for m in (here, there, old):
        db.refresh(m)
    assert here.end_date == ends[here.id] + dt.timedelta(days=9)
    assert there.end_date == ends[there.id] + dt.timedelta(days=2)
    # Lapsed memberships are not revived.
    assert old.end_date == ends[old.id]


def test_freeze_moves_the_end_date(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    membership, _ = sell(db, gym_a, make_member(db, gym_a))
    end = membership.end_date
    sign_in(db, client, gym_a.owner)
    url = f"/api/v1/memberships/{membership.id}/freeze"
    frozen = client.post(
        url,
        json={
            "from_date": TODAY.isoformat(),
            "to_date": (TODAY + dt.timedelta(days=9)).isoformat(),
            "reason": "travel",
        },
    ).json()
    assert frozen["status"] == "frozen"
    assert frozen["end_date"] == (end + dt.timedelta(days=10)).isoformat()

    overlapping = client.post(
        url, json={"from_date": TODAY.isoformat(), "to_date": TODAY.isoformat()}
    )
    assert overlapping.status_code == 409

    # Ending a freeze that started today gives every day back.
    freeze_id = frozen["freezes"][0]["id"]
    ended = client.post(
        f"/api/v1/memberships/{membership.id}/freezes/{freeze_id}/end"
    ).json()
    assert ended["status"] == "active"
    assert ended["end_date"] == end.isoformat()


def test_cancel_with_a_refund(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a)
    membership, _ = sell(db, gym_a, member, paid=1500_00)
    sign_in(db, client, gym_a.owner)
    url = f"/api/v1/memberships/{membership.id}/cancel"
    too_much = client.post(
        url,
        json={
            "reason": "moving abroad",
            "refund": {"amount": 2000_00, "method": "cash"},
        },
    )
    assert too_much.json()["code"] == "refund_too_large"
    response = client.post(
        url,
        json={
            "reason": "moving abroad",
            "refund": {"amount": 1000_00, "method": "cash"},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["membership"]["status"] == "cancelled"
    assert response.json()["payment"]["kind"] == "refund"
    detail = client.get(f"/api/v1/members/{member.id}").json()
    assert detail["dues"] == 0
    assert detail["status"] == "none"


def test_delete_only_a_mistake(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    paid, payment = sell(db, gym_a, make_member(db, gym_a), paid=100_00)
    unpaid, _ = sell(db, gym_a, make_member(db, gym_a, phone="9800000005"))
    sign_in(db, client, gym_a.owner)
    refused = client.delete(f"/api/v1/memberships/{paid.id}")
    assert refused.json()["code"] == "membership_has_payments"
    client.post(f"/api/v1/payments/{payment.id}/void", json={"reason": "wrong member"})
    assert client.delete(f"/api/v1/memberships/{paid.id}").status_code == 204
    assert client.delete(f"/api/v1/memberships/{unpaid.id}").status_code == 204
    assert client.get(f"/api/v1/memberships/{unpaid.id}").status_code == 404
