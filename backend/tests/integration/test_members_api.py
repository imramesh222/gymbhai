import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.time import today_in_nepal
from tests.conftest import GymFixture, make_member, priced_plan, sell, sign_in

TODAY = today_in_nepal()


def add(client: TestClient, **fields):
    body = {"name": "Sita Rai", "phone": "9812345678", **fields}
    return client.post("/api/v1/members", json=body)


def test_add_a_member_and_sell_in_one_step(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    plan = priced_plan(db, gym_a.gym, months=3, price=4000_00)
    plan.admission_fee = 1000_00
    db.commit()
    sign_in(db, client, gym_a.owner)

    response = add(
        client,
        membership={
            "plan_id": str(plan.id),
            "discount": 500_00,
            "payment": {
                "amount": 3000_00,
                "method": "esewa",
                "transaction_ref": "ES123",
            },
        },
    )
    assert response.status_code == 201, response.text
    member = response.json()["member"]
    assert member["member_code"] == "GFZ-0001"
    assert member["status"] == "active"
    # 4000 - 500 + 1000 admission on a first membership - 3000 paid
    assert member["dues"] == 1500_00
    [membership] = member["memberships"]
    assert membership["start_date"] == TODAY.isoformat()
    assert membership["admission_fee"] == 1000_00
    [payment] = member["payments"]
    assert payment["receipt_no"] == 1
    assert payment["received_by_name"] == gym_a.owner.name


def test_member_codes_count_up_per_gym(
    client: TestClient, db: Session, gym_a: GymFixture, gym_b: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    codes = [
        add(client, phone=f"981000000{i}").json()["member"]["member_code"]
        for i in range(3)
    ]
    assert codes == ["GFZ-0001", "GFZ-0002", "GFZ-0003"]
    # Gym B has its own counter.
    assert make_member(db, gym_b).member_code == "GIH-0001"


def test_a_shared_phone_is_allowed_but_flagged(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    add(client, name="Parent")
    assert [
        m["name"]
        for m in client.get("/api/v1/members/phone-check?phone=+977 981-2345678").json()
    ] == ["Parent"]
    second = add(client, name="Child")
    assert second.status_code == 201
    assert [m["name"] for m in second.json()["same_phone"]] == ["Parent"]


def test_search_by_name_phone_or_code(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    add(client, name="Sita Rai", phone="9812345678")
    add(client, name="Ram Thapa", phone="9867654321")

    def names(query: str) -> list[str]:
        items = client.get("/api/v1/members", params={"q": query}).json()["items"]
        return [m["name"] for m in items]

    assert names("sita") == ["Sita Rai"]
    assert names("765432") == ["Ram Thapa"]
    assert names("GFZ-0002") == ["Ram Thapa"]


def test_filters_by_status_and_dues(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    active = make_member(db, gym_a, name="Active", phone="9811000001")
    sell(db, gym_a, active, paid=1500_00)
    owing = make_member(db, gym_a, name="Owing", phone="9811000002")
    sell(db, gym_a, owing, paid=500_00)
    lapsed = make_member(db, gym_a, name="Lapsed", phone="9811000003")
    sell(
        db,
        gym_a,
        lapsed,
        paid=1500_00,
        start_date=TODAY - dt.timedelta(days=60),
        end_date=TODAY - dt.timedelta(days=30),
    )
    make_member(db, gym_a, name="Never", phone="9811000004")
    sign_in(db, client, gym_a.owner)

    def names(**params) -> list[str]:
        return [
            m["name"]
            for m in client.get("/api/v1/members", params=params).json()["items"]
        ]

    assert names(status="active") == ["Active", "Owing"]
    assert names(status="expired") == ["Lapsed"]
    assert names(status="none") == ["Never"]
    assert names(has_dues="true") == ["Owing"]
    assert names(expiring_within=40) == ["Active", "Owing"]


def test_early_renewal_starts_the_day_after(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a)
    current, _ = sell(db, gym_a, member, paid=1500_00)
    plan = priced_plan(db, gym_a.gym)
    plan.admission_fee = 1000_00
    db.commit()
    sign_in(db, client, gym_a.owner)

    response = client.post(
        f"/api/v1/members/{member.id}/memberships", json={"plan_id": str(plan.id)}
    )
    assert response.status_code == 201, response.text
    renewal = response.json()["membership"]
    assert (
        renewal["start_date"] == (current.end_date + dt.timedelta(days=1)).isoformat()
    )
    # No admission fee on a renewal.
    assert renewal["admission_fee"] == 0
    assert renewal["status"] == "upcoming"


def test_renewal_after_a_lapse_starts_today(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a)
    sell(
        db,
        gym_a,
        member,
        start_date=TODAY - dt.timedelta(days=60),
        end_date=TODAY - dt.timedelta(days=30),
    )
    plan = priced_plan(db, gym_a.gym)
    sign_in(db, client, gym_a.owner)
    detail = client.get(f"/api/v1/members/{member.id}").json()
    assert detail["renewal_starts_on"] == TODAY.isoformat()
    response = client.post(
        f"/api/v1/members/{member.id}/memberships", json={"plan_id": str(plan.id)}
    )
    assert response.json()["membership"]["start_date"] == TODAY.isoformat()


def test_a_plan_without_a_price_needs_one_at_the_desk(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    unpriced = client.get("/api/v1/plans").json()[0]
    assert unpriced["price"] is None
    url = f"/api/v1/members/{member.id}/memberships"
    response = client.post(url, json={"plan_id": unpriced["id"]})
    assert response.json()["code"] == "plan_has_no_price"
    assert (
        client.post(url, json={"plan_id": unpriced["id"], "price": 1200_00}).status_code
        == 201
    )


def test_prices_are_copied_at_sale(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a)
    membership, _ = sell(db, gym_a, member)
    plan = priced_plan(db, gym_a.gym, price=9999_00)
    assert plan.price == 9999_00
    db.refresh(membership)
    assert membership.price == 1500_00


def test_bs_counting_follows_the_gym(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    from app.core.calendar import from_bs, to_bs

    # gym_a counts in BS (conftest). 5 Baisakh + 3 months ends 4 Shrawan.
    member = make_member(db, gym_a)
    plan = priced_plan(db, gym_a.gym, months=3)
    membership, _ = sell(db, gym_a, member, plan=plan, start_date=from_bs(2083, 1, 5))
    assert to_bs(membership.end_date) == (2083, 4, 4)


def test_member_edits_are_in_the_history(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    response = client.patch(
        f"/api/v1/members/{member.id}", json={"name": "Sita Rai Sharma"}
    )
    assert response.status_code == 200
    assert (
        client.patch(f"/api/v1/members/{member.id}", json={"name": None}).status_code
        == 422
    )
    history = client.get(f"/api/v1/members/{member.id}/history").json()
    assert history[0]["action"] == "member.updated"
    assert history[0]["changes"]["name"] == {
        "before": "Sita Rai",
        "after": "Sita Rai Sharma",
    }
    assert history[0]["actor_name"] == gym_a.owner.name


def test_archived_members_leave_the_list(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    client.post(f"/api/v1/members/{member.id}/archive", json={"reason": "moved away"})
    assert client.get("/api/v1/members").json()["total"] == 0
    assert (
        client.get("/api/v1/members", params={"archived": "true"}).json()["total"] == 1
    )
    # Still there, with history.
    assert client.get(f"/api/v1/members/{member.id}").json()["is_archived"] is True


def test_photo_upload_is_served_by_signed_link(
    client: TestClient, db: Session, gym_a: GymFixture, tmp_path, monkeypatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "media_root", str(tmp_path))
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    jpeg = b"\xff\xd8\xff\xe0" + b"\0" * 100
    response = client.post(
        f"/api/v1/members/{member.id}/photo",
        files={"file": ("me.jpg", jpeg, "image/jpeg")},
    )
    assert response.status_code == 200, response.text
    url = response.json()["photo_url"]
    assert "sig=" in url

    del client.headers["Authorization"]
    image = client.get(url)
    assert image.status_code == 200
    assert image.content == jpeg
    assert image.headers["content-type"] == "image/jpeg"
    # A tampered link is not found.
    assert client.get(url.replace("sig=", "sig=0")).status_code == 404


def test_uploads_must_be_images(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    response = client.post(
        f"/api/v1/members/{member.id}/photo",
        files={"file": ("x.jpg", b"<script>alert(1)</script>", "image/jpeg")},
    )
    assert response.status_code == 415
