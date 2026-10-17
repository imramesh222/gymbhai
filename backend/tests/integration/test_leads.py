"""Enquiries, trials and referrals (PLAN.md §16.4, 9.1, 9.2, 9.6)."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import Permission
from app.core.time import today_in_nepal
from app.models.activity import ActivityLog
from app.models.lead import Lead
from tests.conftest import GymFixture, make_member, priced_plan, sign_in

TODAY = today_in_nepal()


@pytest.fixture(autouse=True)
def files_in_a_scratch_folder(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "media_root", str(tmp_path))


def add(client: TestClient, **fields):
    body = {
        "name": "Bikash Gurung",
        "phone": "9800000801",
        "source": "walk_in",
        **fields,
    }
    return client.post("/api/v1/leads", json=body)


def test_an_enquiry_through_to_joining(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    plan = priced_plan(db, gym_a.gym)
    sign_in(db, client, gym_a.owner)
    created = add(client, plan_id=str(plan.id), follow_up_on=str(TODAY))
    assert created.status_code == 201, created.text
    lead = created.json()
    assert lead["status"] == "new" and lead["plan_name"] == plan.name

    today = client.get("/api/v1/dashboard/today").json()
    assert today["leads_due"] == 1
    assert today["leads_due_list"][0]["name"] == "Bikash Gurung"

    moved = client.patch(f"/api/v1/leads/{lead['id']}", json={"status": "contacted"})
    assert moved.json()["status"] == "contacted"
    trial = client.post(f"/api/v1/leads/{lead['id']}/trial").json()
    assert trial["status"] == "trial" and trial["trial_on"] == str(TODAY)

    # Convert: Add member with the enquiry linked.
    joined = client.post(
        "/api/v1/members",
        json={"name": "Bikash Gurung", "phone": "9800000801", "lead_id": lead["id"]},
    )
    assert joined.status_code == 201, joined.text
    member_id = joined.json()["member"]["id"]
    after = client.get(f"/api/v1/leads/{lead['id']}").json()
    assert (after["status"], after["member_id"]) == ("joined", member_id)
    assert client.get("/api/v1/dashboard/today").json()["leads_due"] == 0
    # Once joined, it's the member that changes, not the enquiry.
    again = client.patch(f"/api/v1/leads/{lead['id']}", json={"status": "new"})
    assert again.status_code == 409
    twice = client.post(
        "/api/v1/members",
        json={"name": "Bikash G", "phone": "9800000802", "lead_id": lead["id"]},
    )
    assert twice.status_code == 409

    actions = set(
        db.scalars(select(ActivityLog.action).where(ActivityLog.entity == "lead"))
    )
    assert {"lead.created", "lead.updated", "lead.trial", "lead.joined"} <= actions


def test_lost_needs_a_reason(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    lead_id = add(client).json()["id"]
    url = f"/api/v1/leads/{lead_id}"
    assert client.patch(url, json={"status": "lost"}).status_code == 422
    lost = client.patch(url, json={"status": "lost", "lost_reason": "Too far"})
    assert lost.json()["lost_reason"] == "Too far"
    # Back to contacted: the reason goes.
    assert client.patch(url, json={"status": "contacted"}).json()["lost_reason"] is None
    # Some way to reach them.
    assert add(client, phone=None).status_code == 422


def test_a_known_phone_is_a_warning(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a, phone="9800000811", name="Sita")
    sign_in(db, client, gym_a.owner)
    add(client, phone="9800000812", name="Asked before")
    found = client.get("/api/v1/leads/phone-check?phone=9800000811").json()
    assert found == [
        {
            "id": str(member.id),
            "name": "Sita",
            "kind": "member",
            "detail": member.member_code,
        }
    ]
    asked = client.get("/api/v1/leads/phone-check?phone=980-000-0812").json()
    assert [(m["kind"], m["detail"]) for m in asked] == [("lead", "new")]


def test_referrals(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    friend = make_member(db, gym_a, phone="9800000821", name="Ram")
    sign_in(db, client, gym_a.owner)
    lead = add(client, referred_by_id=str(friend.id), source="walk_in").json()
    assert lead["source"] == "referral" and lead["referred_by_name"] == "Ram"
    joined = client.post(
        "/api/v1/members",
        json={"name": "Bikash", "phone": "9800000801", "lead_id": lead["id"]},
    ).json()["member"]
    assert joined["referred_by_id"] == str(friend.id)
    assert joined["referred_by_name"] == "Ram"
    # And one who came straight to the desk, naming Ram.
    client.post(
        "/api/v1/members",
        json={"name": "Hari", "phone": "9800000822", "referred_by_id": str(friend.id)},
    )
    report = client.get("/api/v1/leads/report").json()
    [top] = report["top_referrers"]
    assert (top["name"], top["referred"], top["joined"]) == ("Ram", 2, 2)
    # Not themselves.
    me = client.patch(
        f"/api/v1/members/{friend.id}", json={"referred_by_id": str(friend.id)}
    )
    assert me.status_code == 422


def test_report_by_source(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    sign_in(db, client, gym_a.owner)
    a = add(client, phone="9800000831", source="facebook").json()
    add(client, phone="9800000832", source="facebook")
    add(client, phone="9800000833", source="instagram")
    client.post(f"/api/v1/leads/{a['id']}/trial")
    client.post(
        "/api/v1/members",
        json={"name": "Joined", "phone": "9800000831", "lead_id": a["id"]},
    )
    report = client.get("/api/v1/leads/report").json()
    rows = {r["source"]: r for r in report["rows"]}
    assert (rows["facebook"]["enquiries"], rows["facebook"]["trials"]) == (2, 1)
    assert rows["facebook"]["joined"] == 1 and rows["facebook"]["conversion"] == 0.5
    assert rows["instagram"]["conversion"] == 0
    assert rows["tiktok"]["conversion"] is None
    assert report["total"]["enquiries"] == 3


def test_only_with_enquiries_permission(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
) -> None:
    desk = make_staff(gym_a.gym, permissions=[Permission.MEMBERS_VIEW])
    sign_in(db, client, desk)
    assert client.get("/api/v1/leads").status_code == 403
    assert add(client).status_code == 403


def test_erasing_the_member_scrubs_their_enquiry(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    lead = add(client, notes="Knee injury").json()
    member = client.post(
        "/api/v1/members",
        json={"name": "Bikash", "phone": "9800000801", "lead_id": lead["id"]},
    ).json()["member"]
    assert client.post(f"/api/v1/members/{member['id']}/erase").status_code == 200
    row = db.get(Lead, lead["id"])
    db.refresh(row)
    assert (row.name, row.phone, row.notes) == ("Erased member", None, None)
    histories = db.scalars(
        select(ActivityLog.changes).where(ActivityLog.entity_id == row.id)
    ).all()
    assert all(changes is None for changes in histories)


def test_follow_ups_on_today_only_when_due(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    add(client, phone="9800000841", follow_up_on=str(TODAY + dt.timedelta(days=2)))
    add(client, phone="9800000842", follow_up_on=str(TODAY - dt.timedelta(days=1)))
    today = client.get("/api/v1/dashboard/today").json()
    assert today["leads_due"] == 1
