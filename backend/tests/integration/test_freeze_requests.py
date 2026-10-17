"""Freeze requests from the member app (PLAN.md §16.3, 8.6)."""

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import Permission
from app.core.time import today_in_nepal
from app.models.membership import Membership, MembershipFreeze
from app.models.messaging import SmsMessage
from app.services import member_auth
from tests.conftest import GymFixture, make_member, sell, sign_in

TODAY = today_in_nepal()


def as_member(db: Session, client: TestClient, member) -> None:
    issued = member_auth.start_session(db, member, None)
    db.commit()
    client.headers["Authorization"] = f"Bearer {issued.access_token}"


def ask(client: TestClient, start: int = 3, end: int = 12, reason: str = "Going home"):
    return client.post(
        "/api/v1/m/freeze-requests",
        json={
            "from_date": str(TODAY + dt.timedelta(days=start)),
            "to_date": str(TODAY + dt.timedelta(days=end)),
            "reason": reason,
        },
    )


def member_with_month(db: Session, gym: GymFixture, phone: str = "9800000701"):
    member = make_member(db, gym, phone=phone)
    membership, _ = sell(db, gym, member, paid=1500_00, start_date=TODAY,
                         end_date=TODAY + dt.timedelta(days=29))  # fmt: skip
    return member, membership


def test_ask_then_approved(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    member, membership = member_with_month(db, gym_a)
    as_member(db, client, member)
    asked = ask(client)
    assert asked.status_code == 201, asked.text
    assert ask(client).status_code == 409  # one waiting at a time
    assert client.get("/api/v1/m/freeze-requests/latest").json()["status"] == "pending"

    client.headers.pop("Authorization")
    sign_in(db, client, gym_a.owner)
    assert client.get("/api/v1/freeze-requests/count").json() == {"pending": 1}
    [waiting] = client.get("/api/v1/freeze-requests").json()
    assert waiting["member_name"] == member.name
    approved = client.post(f"/api/v1/freeze-requests/{waiting['id']}/approve")
    assert approved.json()["status"] == "approved"
    assert approved.json()["reviewed_by_name"] == gym_a.owner.name

    # An ordinary freeze: ten days, so the membership ends ten days later.
    db.refresh(membership)
    assert membership.end_date == TODAY + dt.timedelta(days=39)
    assert db.scalars(select(MembershipFreeze)).one().reason == "Going home"
    assert (
        client.post(f"/api/v1/freeze-requests/{waiting['id']}/approve").status_code
        == 409
    )
    # The member hears (by SMS: no push on this phone).
    told = db.scalars(select(SmsMessage).where(SmsMessage.member_id == member.id)).all()
    assert any("frozen from" in sms.body for sms in told)


def test_rejected_with_a_reason(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member, membership = member_with_month(db, gym_a)
    as_member(db, client, member)
    request_id = ask(client).json()["id"]
    client.headers.pop("Authorization")
    sign_in(db, client, gym_a.owner)
    rejected = client.post(
        f"/api/v1/freeze-requests/{request_id}/reject",
        json={"reason": "Exams aren't leave"},
    )
    assert rejected.json()["status"] == "rejected"
    db.refresh(membership)
    assert membership.end_date == TODAY + dt.timedelta(days=29)
    as_member(db, client, member)
    latest = client.get("/api/v1/m/freeze-requests/latest").json()
    assert latest["reject_reason"] == "Exams aren't leave"
    assert ask(client).status_code == 201  # may ask again


def test_what_can_be_asked(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    member, _ = member_with_month(db, gym_a)
    as_member(db, client, member)
    assert ask(client, start=-1).status_code == 422  # the past
    assert ask(client, start=5, end=4).status_code == 422
    assert ask(client, start=1, end=200).status_code == 422  # too long for the app
    assert ask(client, start=40, end=45).status_code == 422  # no membership then
    no_plan = make_member(db, gym_a, phone="9800000702", name="New")
    as_member(db, client, no_plan)
    assert ask(client).status_code == 422


def test_withdraw_and_only_your_own(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member, _ = member_with_month(db, gym_a)
    other, _ = member_with_month(db, gym_a, phone="9800000703")
    as_member(db, client, other)
    theirs = ask(client).json()["id"]
    as_member(db, client, member)
    assert (
        client.post(f"/api/v1/m/freeze-requests/{theirs}/withdraw").status_code == 404
    )
    mine = ask(client).json()["id"]
    withdrawn = client.post(f"/api/v1/m/freeze-requests/{mine}/withdraw")
    assert withdrawn.json()["status"] == "withdrawn"


def test_only_staff_who_freeze(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
) -> None:
    member, _ = member_with_month(db, gym_a)
    as_member(db, client, member)
    request_id = ask(client).json()["id"]
    client.headers.pop("Authorization")
    desk = make_staff(gym_a.gym, permissions=[Permission.MEMBERS_VIEW])
    sign_in(db, client, desk)
    assert client.get("/api/v1/freeze-requests").status_code == 403
    assert (
        client.post(f"/api/v1/freeze-requests/{request_id}/approve").status_code == 403
    )
    assert db.scalars(select(Membership)).first() is not None
