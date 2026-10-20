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


def test_a_member_cannot_book_another_gyms_class_or_cancel_anothers_booking(
    client: TestClient, db: Session, gym_a: GymFixture, gym_b: GymFixture
) -> None:
    """Classes (PLAN.md §19.4)."""
    import datetime as dt

    from app.core.time import utcnow
    from app.models.classes import ClassBooking, ClassType, GymClass

    mine = make_member(db, gym_a, phone="9811000001")
    neighbour = make_member(db, gym_a, name="Neighbour", phone="9811000003")
    classes = {}
    for gym in (gym_a, gym_b):
        kind = ClassType(gym_id=gym.gym.id, name="Zumba")
        db.add(kind)
        db.flush()
        classes[gym.gym.id] = GymClass(
            gym_id=gym.gym.id,
            branch_id=gym.branch.id,
            type_id=kind.id,
            starts_at=utcnow() + dt.timedelta(days=1),
            ends_at=utcnow() + dt.timedelta(days=1, hours=1),
            places=5,
        )
        db.add(classes[gym.gym.id])
    db.flush()
    theirs = ClassBooking(
        gym_id=gym_a.gym.id,
        class_id=classes[gym_a.gym.id].id,
        member_id=neighbour.id,
        status="booked",
        booked_at=utcnow(),
    )
    db.add(theirs)
    db.commit()

    member_client(db, client, mine)
    other_gyms = classes[gym_b.gym.id]
    assert client.post(f"/api/v1/m/classes/{other_gyms.id}/book").status_code == 404
    response = client.post(f"/api/v1/m/class-bookings/{theirs.id}/cancel")
    assert response.status_code == 404


def test_a_member_cannot_touch_anothers_progress(
    client: TestClient, db: Session, gym_a: GymFixture, gym_b: GymFixture
) -> None:
    """Progress (PLAN.md §19.5): their weight and photos are theirs alone."""
    from app.core.time import today_in_nepal
    from app.models.progress import ProgressEntry, ProgressPhoto

    mine = make_member(db, gym_a, phone="9811000001")
    neighbour = make_member(db, gym_a, name="Neighbour", phone="9811000003")
    elsewhere = make_member(db, gym_b, phone="9811000002")
    entries, photos = [], []
    for member in (neighbour, elsewhere):
        entry = ProgressEntry(
            gym_id=member.gym_id,
            member_id=member.id,
            measured_on=today_in_nepal(),
            weight_g=70_000,
        )
        photo = ProgressPhoto(
            gym_id=member.gym_id,
            member_id=member.id,
            taken_on=today_in_nepal(),
            pose="front",
            photo_key="x/progress/x.jpg",
        )
        db.add_all([entry, photo])
        entries.append(entry)
        photos.append(photo)
    db.commit()

    member_client(db, client, mine)
    for entry in entries:
        path = f"/api/v1/m/progress/{entry.id}"
        assert client.patch(path, json={"weight_g": 1}).status_code in (404, 422)
        assert client.delete(path).status_code == 404
    for photo in photos:
        path = f"/api/v1/m/progress/photos/{photo.id}"
        assert client.patch(path, json={"shared": True}).status_code == 404
        assert client.delete(path).status_code == 404
    assert client.get("/api/v1/m/progress").json()["entries"] == []
