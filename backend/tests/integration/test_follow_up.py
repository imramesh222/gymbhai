"""Follow up (PLAN.md §16.3, 8.1): who to chase, including members who are
paid up but have stopped coming."""

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.time import NEPAL, today_in_nepal
from app.models.member_app import ALLOWED, DENIED_EXPIRED, CheckIn
from tests.conftest import GymFixture, make_member, sell, sign_in

TODAY = today_in_nepal()


def days_ago(days: int) -> dt.datetime:
    return dt.datetime.combine(TODAY - dt.timedelta(days=days), dt.time(7), NEPAL)


def member(db: Session, gym: GymFixture, phone: str, *, joined: int, **sale):
    """Joined `joined` days ago, with a month that covers today."""
    m = make_member(db, gym, phone=phone, name=f"Member {phone[-2:]}")
    m.created_at = days_ago(joined)
    sell(
        db,
        gym,
        m,
        start_date=sale.pop("start", TODAY - dt.timedelta(days=10)),
        end_date=sale.pop("end", TODAY + dt.timedelta(days=20)),
        **sale,
    )
    return m


def visit(db: Session, gym: GymFixture, m, days: int, result: str = ALLOWED) -> None:
    db.add(
        CheckIn(
            gym_id=gym.gym.id,
            branch_id=gym.branch.id,
            member_id=m.id,
            at=days_ago(days),
            method="manual",
            result=result,
        )
    )
    db.commit()


def ids(items: list[dict]) -> list[str]:
    return [item["id"] for item in items]


def test_not_visiting(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    stopped = member(db, gym_a, "9800000201", joined=60, paid=1500_00)
    visit(db, gym_a, stopped, 20)
    visit(db, gym_a, stopped, 1, DENIED_EXPIRED)  # turned away is not a visit
    never = member(db, gym_a, "9800000202", joined=60, paid=1500_00)
    regular = member(db, gym_a, "9800000203", joined=60, paid=1500_00)
    visit(db, gym_a, regular, 3)
    member(db, gym_a, "9800000204", joined=5, paid=1500_00)  # hasn't had the chance
    lapsed = member(
        db,
        gym_a,
        "9800000205",
        joined=60,
        paid=1500_00,
        start=TODAY - dt.timedelta(days=40),
        end=TODAY - dt.timedelta(days=10),
    )
    sign_in(db, client, gym_a.owner)

    lists = client.get("/api/v1/lists/follow-up").json()
    # Most recently stopped first: they are the easiest to win back.
    assert ids(lists["not_visiting"]) == [str(stopped.id), str(never.id)]
    assert lists["not_visiting_total"] == 2
    assert lists["not_visiting_days"] == 14
    assert lists["not_visiting"][0]["last_visit_at"].startswith(
        str(TODAY - dt.timedelta(days=20))
    )
    assert lists["not_visiting"][1]["last_visit_at"] is None
    assert ids(lists["lapsed"]) == [str(lapsed.id)]

    listed = client.get("/api/v1/members?not_visiting=true").json()
    assert {m["id"] for m in listed["items"]} == {str(stopped.id), str(never.id)}
    assert client.get("/api/v1/members/counts").json()["not_visiting"] == 2
    assert client.get("/api/v1/dashboard/today").json()["not_visiting"] == 2

    # The gym decides how long is too long.
    response = client.patch(
        "/api/v1/gym/check-in-rules", json={"not_visiting_days": 30}
    )
    assert response.status_code == 200
    lists = client.get("/api/v1/lists/follow-up").json()
    assert ids(lists["not_visiting"]) == [str(never.id)]
    assert client.get("/api/v1/dashboard/today").json()["not_visiting"] == 1
    bad = client.patch("/api/v1/gym/check-in-rules", json={"not_visiting_days": 1})
    assert bad.status_code == 422


def test_owing(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    little = member(db, gym_a, "9800000211", joined=60, paid=1000_00)
    lots = member(db, gym_a, "9800000212", joined=60)
    member(db, gym_a, "9800000213", joined=60, paid=1500_00)
    sign_in(db, client, gym_a.owner)
    lists = client.get("/api/v1/lists/follow-up").json()
    assert ids(lists["owing"]) == [str(lots.id), str(little.id)]
    assert lists["owing_total"] == 2
    assert [m["dues"] for m in lists["owing"]] == [1500_00, 500_00]
