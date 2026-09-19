"""Members only ever see their own records (PLAN.md §11), and the two kinds of
sign-in never stand in for each other."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.member_app import PaymentRequest
from app.services import member_auth
from tests.conftest import GymFixture, make_member, sell, sign_in


def member_client(db: Session, client: TestClient, member) -> None:
    issued = member_auth.start_session(db, member, None)
    db.commit()
    client.headers["Authorization"] = f"Bearer {issued.access_token}"


def test_a_member_cannot_touch_another_members_request(
    client: TestClient, db: Session, gym_a: GymFixture, gym_b: GymFixture
) -> None:
    mine = make_member(db, gym_a, phone="9811000001")
    theirs = make_member(db, gym_b, phone="9811000002")
    neighbour = make_member(db, gym_a, name="Neighbour", phone="9811000003")
    for member, gym in ((theirs, gym_b), (neighbour, gym_a)):
        membership, _ = sell(db, gym, member)
        db.add(
            PaymentRequest(
                gym_id=member.gym_id,
                member_id=member.id,
                plan_id=membership.plan_id,
                amount=100,
                status="pending",
            )
        )
    db.commit()
    other_requests = db.query(PaymentRequest).all()

    member_client(db, client, mine)
    for row in other_requests:
        response = client.post(f"/api/v1/m/payment-requests/{row.id}/withdraw")
        assert response.status_code == 404
    assert client.get("/api/v1/m/me/payments").json()["requests"] == []


def test_a_member_token_is_not_a_staff_token(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member_client(db, client, make_member(db, gym_a))
    assert client.get("/api/v1/m/me").status_code == 200
    assert client.get("/api/v1/gym").status_code == 401
    assert client.get("/api/v1/members").status_code == 401


def test_a_staff_token_is_not_a_member_token(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    assert client.get("/api/v1/m/me").status_code == 401


def test_the_member_app_only_knows_its_own_gyms_members(
    client: TestClient, db: Session, gym_a: GymFixture, gym_b: GymFixture
) -> None:
    """The same number at another gym gets the plain "not registered" answer."""
    make_member(db, gym_b, phone="9811000009")
    response = client.post(
        "/api/v1/m/fitness-zone/otp/request", json={"phone": "9811000009"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == (
        "This number isn't registered with Gym fitness-zone. Please ask at the desk."
    )
