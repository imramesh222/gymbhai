"""One gym can never read or change another gym's data (PLAN.md §3, §11).

Signed in as gym A's owner — who holds every permission — every attempt on
gym B's records by id must be a 404, not a 403, which would confirm the id
exists. Every route that takes an id must be listed in CROSS_GYM_ROUTES;
`test_every_id_route_is_covered` fails until it is.
"""

import datetime as dt
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.gym import Gym
from app.models.member_app import Device, PaymentRequest
from app.models.messaging import Notice, ReminderRule
from app.models.payment import GymPaymentMethod
from app.services import memberships as ms
from tests.conftest import (
    GymFixture,
    context_for,
    make_member,
    sell,
    sign_in,
)
from tests.routes import all_routes

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


@dataclass
class World:
    """Gym B, with one of everything."""

    ids: dict[str, Any]


@pytest.fixture
def world_b(db: Session, gym_b: GymFixture, make_staff) -> World:
    member = make_member(db, gym_b, phone="9819999999")
    membership, payment = sell(db, gym_b, member, paid=500_00)
    freeze = ms.freeze(
        db,
        context_for(db, gym_b.owner),
        membership,
        membership.end_date,
        membership.end_date,
        "injury",
    )
    method = GymPaymentMethod(gym_id=gym_b.gym.id, kind="esewa", label="eSewa")
    notice = Notice(
        gym_id=gym_b.gym.id, title="B only", body="Secret", published_at=utcnow()
    )
    db.add_all([method, notice])
    rule = db.scalars(
        select(ReminderRule).where(ReminderRule.gym_id == gym_b.gym.id)
    ).first()
    staff = make_staff(gym_b.gym)
    device = Device(
        gym_id=gym_b.gym.id,
        branch_id=gym_b.branch.id,
        name="B door",
        token_hash="b" * 64,
    )
    b_request = PaymentRequest(
        gym_id=gym_b.gym.id,
        member_id=member.id,
        plan_id=membership.plan_id,
        amount=1500_00,
        status="pending",
    )
    db.add_all([device, b_request])
    db.commit()
    return World(
        ids={
            "branch_id": gym_b.branch.id,
            "staff_id": staff.id,
            "plan_id": membership.plan_id,
            "method_id": method.id,
            "member_id": member.id,
            "membership_id": membership.id,
            "freeze_id": freeze.id,
            "payment_id": payment.id,
            "rule_id": rule.id,
            "notice_id": notice.id,
            "device_id": device.id,
            "request_id": b_request.id,
        }
    )


TODAY = dt.date.today().isoformat()

# (method, path, JSON body or "upload")
CROSS_GYM_ROUTES: list[tuple[str, str, Any]] = [
    ("GET", "/api/v1/branches/{branch_id}", None),
    ("PATCH", "/api/v1/branches/{branch_id}", {"name": "Taken"}),
    ("PATCH", "/api/v1/staff/{staff_id}", {"name": "Taken"}),
    ("POST", "/api/v1/staff/{staff_id}/password", {"new_password": "taken-over-123"}),
    ("PATCH", "/api/v1/plans/{plan_id}", {"price": 1}),
    ("PATCH", "/api/v1/payment-methods/{method_id}", {"label": "Taken"}),
    ("POST", "/api/v1/payment-methods/{method_id}/qr", "upload"),
    ("GET", "/api/v1/members/{member_id}", None),
    ("PATCH", "/api/v1/members/{member_id}", {"name": "Taken"}),
    ("POST", "/api/v1/members/{member_id}/archive", {}),
    ("POST", "/api/v1/members/{member_id}/unarchive", None),
    ("POST", "/api/v1/members/{member_id}/photo", "upload"),
    ("POST", "/api/v1/members/{member_id}/memberships", "own_plan"),
    ("GET", "/api/v1/members/{member_id}/history", None),
    ("GET", "/api/v1/memberships/{membership_id}", None),
    ("PATCH", "/api/v1/memberships/{membership_id}", {"discount": 1}),
    (
        "POST",
        "/api/v1/memberships/{membership_id}/extend",
        {"days": 1, "reason": "why not"},
    ),
    (
        "POST",
        "/api/v1/memberships/{membership_id}/freeze",
        {"from_date": TODAY, "to_date": TODAY},
    ),
    ("POST", "/api/v1/memberships/{membership_id}/freezes/{freeze_id}/end", None),
    ("POST", "/api/v1/memberships/{membership_id}/cancel", {"reason": "taken over"}),
    ("DELETE", "/api/v1/memberships/{membership_id}", None),
    ("GET", "/api/v1/memberships/{membership_id}/history", None),
    ("PATCH", "/api/v1/payments/{payment_id}", {"note": "taken"}),
    ("POST", "/api/v1/payments/{payment_id}/void", {"reason": "taken over"}),
    ("GET", "/api/v1/payments/{payment_id}/receipt", None),
    ("POST", "/api/v1/members/{member_id}/sms", {"body": "Hello"}),
    ("PATCH", "/api/v1/reminder-rules/{rule_id}", {"enabled": False}),
    ("DELETE", "/api/v1/reminder-rules/{rule_id}", None),
    ("DELETE", "/api/v1/notices/{notice_id}", None),
    ("POST", "/api/v1/devices/{device_id}/revoke", None),
    ("POST", "/api/v1/payment-requests/{request_id}/approve", {}),
    ("POST", "/api/v1/payment-requests/{request_id}/reject", {"reason": "taken over"}),
    ("PATCH", "/api/v1/members/{member_id}/access", {"app_access": False}),
    ("POST", "/api/v1/members/{member_id}/sign-out-all", None),
    ("POST", "/api/v1/members/{member_id}/resend-welcome", None),
    ("POST", "/api/v1/members/{member_id}/qr/reissue", None),
    ("POST", "/api/v1/members/{member_id}/card/reissue", None),
    ("GET", "/api/v1/members/{member_id}/card", None),
]

# Id routes whose permission is not the gym at all.
NOT_GYM_SCOPED = {
    ("GET", "/api/v1/files/{key}"),
    # Public, by the gym's own address.
    ("GET", "/api/v1/m/{slug}/gym"),
    ("GET", "/api/v1/m/{slug}/logo"),
    ("POST", "/api/v1/m/{slug}/otp/request"),
    ("POST", "/api/v1/m/{slug}/otp/verify"),
    # The member's own records: tests/regression/test_member_isolation.py.
    ("POST", "/api/v1/m/payment-requests/{request_id}/screenshot"),
    ("POST", "/api/v1/m/payment-requests/{request_id}/withdraw"),
}


@pytest.mark.parametrize(
    ("method", "path", "body"),
    CROSS_GYM_ROUTES,
    ids=[f"{m} {p}" for m, p, _ in CROSS_GYM_ROUTES],
)
def test_another_gyms_record_is_not_found(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    world_b: World,
    method: str,
    path: str,
    body: Any,
) -> None:
    sign_in(db, client, gym_a.owner)
    url = path.format(**world_b.ids)
    if body == "upload":
        response = client.request(
            method, url, files={"file": ("x.png", PNG, "image/png")}
        )
    elif body == "own_plan":
        # Gym A's own plan, gym B's member: still not found.
        from tests.conftest import priced_plan

        plan = priced_plan(db, gym_a.gym)
        response = client.request(method, url, json={"plan_id": str(plan.id)})
    else:
        response = client.request(method, url, json=body)
    assert response.status_code == 404, response.text
    assert response.json()["code"] == "not_found"


def test_every_id_route_is_covered() -> None:
    covered = {(m, p) for m, p, _ in CROSS_GYM_ROUTES} | NOT_GYM_SCOPED
    for method, path, _ in all_routes():
        if "{" in path:
            assert (method, path) in covered, (
                f"{method} {path} takes an id: add it to CROSS_GYM_ROUTES"
            )


def test_nothing_of_gym_b_changed(
    client: TestClient, db: Session, gym_a: GymFixture, world_b: World
) -> None:
    """Run every attempt, then check gym B's rows are exactly as they were."""
    from app.models.member import Member
    from app.models.membership import Membership
    from app.models.payment import Payment

    member = db.get(Member, world_b.ids["member_id"])
    membership = db.get(Membership, world_b.ids["membership_id"])
    before = (member.name, membership.end_date, membership.discount)
    sign_in(db, client, gym_a.owner)
    for method, path, body in CROSS_GYM_ROUTES:
        if body not in ("upload", "own_plan"):
            client.request(method, path.format(**world_b.ids), json=body)
    for row in (member, membership):
        db.refresh(row)
    assert (member.name, membership.end_date, membership.discount) == before
    assert membership.cancelled_at is None
    assert db.get(Payment, world_b.ids["payment_id"]).voided_at is None


def test_lists_only_show_your_own_gym(
    client: TestClient, db: Session, gym_a: GymFixture, world_b: World
) -> None:
    sign_in(db, client, gym_a.owner)
    assert {b["id"] for b in client.get("/api/v1/branches").json()} == {
        str(gym_a.branch.id)
    }
    assert client.get("/api/v1/gym").json()["id"] == str(gym_a.gym.id)
    assert client.get("/api/v1/members").json()["total"] == 0
    assert client.get("/api/v1/payments").json()["total"] == 0
    assert client.get("/api/v1/payment-methods").json() == []
    assert client.get("/api/v1/notices").json() == []
    assert client.get("/api/v1/sms").json()["items"] == []
    assert client.get("/api/v1/lists/expiring").json() == {
        "due_today": [],
        "due_this_week": [],
        "lapsed": [],
    }
    plan_ids = {p["id"] for p in client.get("/api/v1/plans").json()}
    assert str(world_b.ids["plan_id"]) not in plan_ids
    staff = client.get("/api/v1/staff").json()
    assert [s["id"] for s in staff] == [str(gym_a.owner.id)]
    # Phone lookups too: another gym's member is never "already on file".
    assert client.get("/api/v1/members/phone-check?phone=9819999999").json() == []


def test_extend_everyone_stays_in_your_gym(
    client: TestClient, db: Session, gym_a: GymFixture, world_b: World
) -> None:
    from app.models.membership import Membership

    membership = db.get(Membership, world_b.ids["membership_id"])
    end = membership.end_date
    sign_in(db, client, gym_a.owner)
    response = client.post(
        "/api/v1/memberships/extend-all", json={"days": 7, "reason": "Dashain"}
    )
    assert response.json() == {"extended": 0}
    db.refresh(membership)
    assert membership.end_date == end


def test_selling_another_gyms_plan_is_refused(
    client: TestClient, db: Session, gym_a: GymFixture, world_b: World
) -> None:
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    response = client.post(
        f"/api/v1/members/{member.id}/memberships",
        json={"plan_id": str(world_b.ids["plan_id"])},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "bad_plan"


def test_paying_into_another_gyms_membership_is_not_found(
    client: TestClient, db: Session, gym_a: GymFixture, world_b: World
) -> None:
    sign_in(db, client, gym_a.owner)
    response = client.post(
        "/api/v1/payments",
        json={
            "membership_id": str(world_b.ids["membership_id"]),
            "amount": 100,
            "method": "cash",
        },
    )
    assert response.status_code == 404


def test_a_gym_id_in_the_body_is_refused_not_obeyed(
    client: TestClient, db: Session, gym_a: GymFixture, gym_b: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    response = client.patch(
        "/api/v1/gym", json={"gym_id": str(gym_b.gym.id), "name": "Hijacked"}
    )
    assert response.status_code == 422
    response = client.post(
        "/api/v1/members",
        json={"name": "X", "phone": "9811111111", "gym_id": str(gym_b.gym.id)},
    )
    assert response.status_code == 422
    assert db.get(Gym, gym_b.gym.id).name == "Gym iron-house"


def test_a_token_is_bound_to_its_gym(
    client: TestClient, db: Session, gym_a: GymFixture, gym_b: GymFixture
) -> None:
    """Moving an account to another gym invalidates the tokens it holds."""
    sign_in(db, client, gym_a.owner)
    gym_a.owner.gym_id = gym_b.gym.id
    gym_a.owner.is_owner = False
    db.commit()
    assert client.get("/api/v1/gym").status_code == 401
