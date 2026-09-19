import datetime as dt
import time
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import qr
from app.core.time import today_in_nepal
from app.models.gym import Branch
from app.models.member_app import CheckIn
from app.models.plan import Plan, PlanBranch
from app.models.staff import StaffUser
from app.services import memberships as ms
from tests.conftest import GymFixture, context_for, make_member, sell, sign_in

TODAY = today_in_nepal()


def app_code(member) -> str:
    key = qr.app_key(member.qr_secret, member.qr_version)
    return qr.app_code(member.id, key, qr.window_at(time.time()))


@pytest.fixture
def kiosk(client: TestClient, db: Session, gym_a: GymFixture) -> TestClient:
    """A registered door scanner at gym A's main branch."""
    sign_in(db, client, gym_a.owner)
    registered = client.post(
        "/api/v1/devices",
        json={"branch_id": str(gym_a.branch.id), "name": "Front door"},
    ).json()
    kiosk = TestClient(client.app)
    kiosk.headers["X-Device-Token"] = registered["token"]
    return kiosk


def scan(kiosk: TestClient, code: str) -> dict:
    response = kiosk.post("/api/v1/kiosk/scan", json={"code": code})
    assert response.status_code == 200, response.text
    return response.json()


def test_the_flow_that_must_never_break(
    db: Session, gym_a: GymFixture, kiosk: TestClient
) -> None:
    """PLAN.md §13: take payment -> scan at kiosk -> allowed; membership ends ->
    denied. (The browser half is e2e/m3-door.spec.ts.)"""
    member = make_member(db, gym_a)
    membership, _ = sell(db, gym_a, member, paid=1500_00)
    first = scan(kiosk, app_code(member))
    assert first["result"] == "allowed" and first["let_in"]
    assert first["member_name"] == "Sita Rai"
    assert first["days_left"] == (membership.end_date - TODAY).days + 1

    membership.end_date = TODAY - dt.timedelta(days=1)
    membership.start_date = TODAY - dt.timedelta(days=30)
    db.commit()
    denied = scan(kiosk, app_code(member))
    assert denied["result"] == "denied_expired" and not denied["let_in"]
    assert db.query(CheckIn).count() == 2  # denied scans are recorded too


def test_already_checked_in(db: Session, gym_a: GymFixture, kiosk: TestClient) -> None:
    member = make_member(db, gym_a)
    sell(db, gym_a, member, paid=1500_00)
    assert scan(kiosk, app_code(member))["result"] == "allowed"
    again = scan(kiosk, app_code(member))
    assert again["result"] == "duplicate" and again["let_in"]


def test_printed_cards_and_reissuing_them(
    client: TestClient, db: Session, gym_a: GymFixture, kiosk: TestClient
) -> None:
    member = make_member(db, gym_a)
    sell(db, gym_a, member, paid=1500_00)
    old_card = qr.card_code(member.card_token)
    assert scan(kiosk, old_card)["result"] == "allowed"

    card = client.post(f"/api/v1/members/{member.id}/card/reissue").json()
    assert card["card_code"] != old_card
    assert scan(kiosk, old_card)["result"] == "unknown"


def test_a_screenshot_and_junk_are_unknown(
    db: Session, gym_a: GymFixture, kiosk: TestClient
) -> None:
    member = make_member(db, gym_a)
    sell(db, gym_a, member, paid=1500_00)
    key = qr.app_key(member.qr_secret, member.qr_version)
    stale = qr.app_code(member.id, key, qr.window_at(time.time()) - 5)
    assert scan(kiosk, stale)["result"] == "unknown"
    assert scan(kiosk, "hello")["result"] == "unknown"


def test_another_gyms_member_is_unknown(
    db: Session, gym_a: GymFixture, gym_b: GymFixture, kiosk: TestClient
) -> None:
    theirs = make_member(db, gym_b)
    sell(db, gym_b, theirs, paid=1500_00)
    assert scan(kiosk, app_code(theirs))["result"] == "unknown"
    assert scan(kiosk, qr.card_code(theirs.card_token))["result"] == "unknown"


def test_frozen_members_are_stopped(
    db: Session, gym_a: GymFixture, kiosk: TestClient
) -> None:
    member = make_member(db, gym_a)
    membership, _ = sell(db, gym_a, member, paid=1500_00)
    ms.freeze(db, context_for(db, gym_a.owner), membership, TODAY, TODAY, "travel")
    db.commit()
    assert scan(kiosk, app_code(member))["result"] == "denied_frozen"


def test_grace_days(
    client: TestClient, db: Session, gym_a: GymFixture, kiosk: TestClient
) -> None:
    member = make_member(db, gym_a)
    sell(
        db,
        gym_a,
        member,
        paid=1500_00,
        start_date=TODAY - dt.timedelta(days=31),
        end_date=TODAY - dt.timedelta(days=2),
    )
    assert scan(kiosk, app_code(member))["result"] == "denied_expired"
    client.patch(
        "/api/v1/gym/check-in-rules", json={"grace_days": 3, "rescan_minutes": 0}
    )
    warned = scan(kiosk, app_code(member))
    assert warned["result"] == "warned" and warned["reason"] == "expired_grace"


@pytest.mark.parametrize(
    ("rule", "result"),
    [("allow", "allowed"), ("warn", "warned"), ("refuse", "denied_dues")],
)
def test_the_dues_rule(
    client: TestClient, db: Session, gym_a: GymFixture, kiosk: TestClient, rule, result
) -> None:
    member = make_member(db, gym_a)
    sell(db, gym_a, member, paid=500_00)
    client.patch("/api/v1/gym/check-in-rules", json={"dues_rule": rule})
    assert scan(kiosk, app_code(member))["result"] == result


def test_plan_limited_to_another_branch(
    db: Session, gym_a: GymFixture, kiosk: TestClient
) -> None:
    other = Branch(gym_id=gym_a.gym.id, name="Koteshwor")
    db.add(other)
    db.flush()
    plan = Plan(
        gym_id=gym_a.gym.id,
        name="Koteshwor only",
        duration_months=1,
        price=1000_00,
        all_branches=False,
    )
    db.add(plan)
    db.flush()
    db.add(PlanBranch(plan_id=plan.id, branch_id=other.id))
    db.commit()
    member = make_member(db, gym_a)
    sell(db, gym_a, member, plan=plan, branch_id=other.id, paid=1000_00)
    assert scan(kiosk, app_code(member))["result"] == "denied_branch"


def test_staff_override_needs_the_permission_and_a_reason(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    member = make_member(db, gym_a)
    body = {"member_id": str(member.id), "branch_id": str(gym_a.branch.id)}

    desk = make_staff(gym_a.gym, permissions=["door.check_in"])
    sign_in(db, client, desk)
    refused = client.post("/api/v1/check-ins/manual", json=body).json()
    assert refused["result"] == "denied_expired" and not refused["can_override"]
    forbidden = client.post("/api/v1/check-ins/manual", json={**body, "override": True})
    assert forbidden.status_code == 403

    manager = make_staff(gym_a.gym, permissions=["door.check_in", "door.override"])
    sign_in(db, client, manager)
    assert client.post("/api/v1/check-ins/manual", json=body).json()["can_override"]
    no_reason = client.post("/api/v1/check-ins/manual", json={**body, "override": True})
    assert no_reason.status_code == 422
    let_in = client.post(
        "/api/v1/check-ins/manual",
        json={**body, "override": True, "note": "paying tomorrow"},
    ).json()
    assert let_in["result"] == "override" and let_in["let_in"]


def test_staff_phone_scanner(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a)
    sell(db, gym_a, member, paid=1500_00)
    sign_in(db, client, gym_a.owner)
    response = client.post(
        "/api/v1/check-ins/scan",
        json={"code": app_code(member), "branch_id": str(gym_a.branch.id)},
    )
    assert response.json()["result"] == "allowed"


def test_a_revoked_kiosk_stops_at_once(
    client: TestClient, db: Session, gym_a: GymFixture, kiosk: TestClient
) -> None:
    assert kiosk.get("/api/v1/kiosk/me").json()["branch_name"] == "Main branch"
    [device] = client.get("/api/v1/devices").json()
    client.post(f"/api/v1/devices/{device['id']}/revoke")
    response = kiosk.get("/api/v1/kiosk/me")
    assert response.status_code == 401
    assert response.json()["code"] == "device_revoked"


def test_a_kiosk_cannot_open_the_dashboard(kiosk: TestClient) -> None:
    assert kiosk.get("/api/v1/members").status_code == 401


def test_a_membership_someone_trained_on_cannot_be_deleted(
    client: TestClient, db: Session, gym_a: GymFixture, kiosk: TestClient
) -> None:
    member = make_member(db, gym_a)
    membership, _ = sell(db, gym_a, member)
    scan(kiosk, app_code(member))
    response = client.delete(f"/api/v1/memberships/{membership.id}")
    assert response.json()["code"] == "membership_has_check_ins"


def test_attendance(
    client: TestClient, db: Session, gym_a: GymFixture, kiosk: TestClient
) -> None:
    ok = make_member(db, gym_a, name="Allowed", phone="9800000001")
    sell(db, gym_a, ok, paid=1500_00)
    lapsed = make_member(db, gym_a, name="Lapsed", phone="9800000002")
    scan(kiosk, app_code(ok))
    scan(kiosk, app_code(lapsed))
    summary = client.get(
        "/api/v1/check-ins/summary",
        params={"date_from": TODAY.isoformat(), "date_to": TODAY.isoformat()},
    ).json()
    assert summary["let_in"] == 1 and summary["denied"] == 1
    assert summary["by_day"] == {TODAY.isoformat(): 1}
    denied = client.get("/api/v1/check-ins", params={"denied_only": "true"}).json()
    assert [c["member_name"] for c in denied["items"]] == ["Lapsed"]
