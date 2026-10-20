"""Visit packs and off-peak plans, enforced at the door (PLAN.md §16.4, 9.3, 9.4)."""

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.time import NEPAL, today_in_nepal, utcnow
from app.services import checkins
from tests.conftest import GymFixture, make_member, sign_in

TODAY = today_in_nepal()


def plan(client: TestClient, **fields) -> dict:
    body = {"name": "10 visits", "duration_months": 1, "price": 3000_00, **fields}
    response = client.post("/api/v1/plans", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def sold(client: TestClient, db: Session, gym: GymFixture, plan_id: str, phone: str):
    member = make_member(db, gym, phone=phone)
    response = client.post(
        f"/api/v1/members/{member.id}/memberships",
        json={"plan_id": plan_id, "payment": {"amount": 3000_00, "method": "cash"}},
    )
    assert response.status_code == 201, response.text
    return member


def check_in(client: TestClient, gym: GymFixture, member, **extra) -> dict:
    return client.post(
        "/api/v1/check-ins/manual",
        json={"member_id": str(member.id), "branch_id": str(gym.branch.id), **extra},
    ).json()


def no_rescan_window(client: TestClient) -> None:
    client.patch("/api/v1/gym/check-in-rules", json={"rescan_minutes": 0})


def test_a_visit_pack(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    sign_in(db, client, gym_a.owner)
    no_rescan_window(client)
    pack = plan(client, visit_limit=3)
    assert pack["visit_limit"] == 3
    member = sold(client, db, gym_a, pack["id"], "9800000901")

    lefts = [check_in(client, gym_a, member)["visits_left"] for _ in range(3)]
    assert lefts == [2, 1, 0]
    refused = check_in(client, gym_a, member)
    assert (refused["result"], refused["reason"]) == (
        "denied_visits_used",
        "visits_used",
    )

    # Used up: ended, whatever the dates say.
    detail = client.get(f"/api/v1/members/{member.id}").json()
    assert detail["status"] == "expired"
    assert detail["memberships"][0]["visits_used"] == 3
    assert detail["memberships"][0]["status"] == "expired"
    assert detail["renewal_starts_on"] == str(TODAY)
    active = client.get("/api/v1/members?status=active").json()["items"]
    assert str(member.id) not in {m["id"] for m in active}
    # Changing the plan later doesn't change what they bought.
    client.patch(f"/api/v1/plans/{pack['id']}", json={"visit_limit": 20})
    assert check_in(client, gym_a, member)["result"] == "denied_visits_used"


def test_the_member_app_counts_down(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    from app.services import member_auth

    sign_in(db, client, gym_a.owner)
    member = sold(client, db, gym_a, plan(client, visit_limit=10)["id"], "9800000902")
    check_in(client, gym_a, member)
    issued = member_auth.start_session(db, member, None)
    db.commit()
    client.headers["Authorization"] = f"Bearer {issued.access_token}"
    state = client.get("/api/v1/m/me").json()["state"]
    assert (state["visit_limit"], state["visits_left"]) == (10, 9)


def window(start: dt.datetime, minutes: int) -> dict:
    local = start.astimezone(NEPAL)
    return {
        "days": [local.weekday()],
        "from": local.strftime("%H:%M"),
        "to": (local + dt.timedelta(minutes=minutes)).strftime("%H:%M"),
    }


def test_off_peak_hours(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    sign_in(db, client, gym_a.owner)
    later = utcnow() + dt.timedelta(hours=3)
    # The hour must end the same day: from 20:00 on, earlier instead.
    if (later + dt.timedelta(minutes=60)).astimezone(NEPAL).date() != TODAY:
        later = utcnow() - dt.timedelta(hours=4)
    closed = plan(client, name="Off-peak", access_hours=[window(later, 60)])
    assert closed["access_hours"][0]["from"] == later.astimezone(NEPAL).strftime(
        "%H:%M"
    )
    member = sold(client, db, gym_a, closed["id"], "9800000903")
    refused = check_in(client, gym_a, member)
    assert (refused["result"], refused["reason"]) == ("denied_hours", "hours")
    assert refused["can_override"]
    let_in = check_in(client, gym_a, member, override=True, note="Exam week")
    assert let_in["result"] == "override"

    now = utcnow() - dt.timedelta(minutes=1)
    open_now = plan(client, name="Now", access_hours=[window(now, 30)])
    other = sold(client, db, gym_a, open_now["id"], "9800000904")
    assert check_in(client, gym_a, other)["result"] == "allowed"


def test_hours_are_checked(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    sign_in(db, client, gym_a.owner)
    bad = [
        [{"days": [7], "from": "06:00", "to": "10:00"}],
        [{"days": [0], "from": "10:00", "to": "06:00"}],
        [{"days": [], "from": "06:00", "to": "10:00"}],
        [{"days": [0], "from": "6am", "to": "10:00"}],
    ]
    for hours in bad:
        response = client.post(
            "/api/v1/plans",
            json={"name": "x", "duration_months": 1, "access_hours": hours},
        )
        assert response.status_code == 422, hours
    whole_evening = {"days": [5, 6], "from": "18:00", "to": "24:00"}
    assert plan(client, name="Weekend nights", access_hours=[whole_evening])
    assert checkins.within_hours(
        [whole_evening | {"days": [5]}],
        dt.datetime(2026, 10, 17, 23, 59, tzinfo=NEPAL),  # a Saturday
    )
