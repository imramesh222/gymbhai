"""What's new, and gyms sending us gyms (PLAN.md §16.5, 10.4, 10.5)."""

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.billing import PlatformPlan
from app.models.gym import Gym
from app.models.platform import GymReferral
from app.models.staff import StaffUser
from app.services import subscription
from tests.conftest import GymFixture, sign_in


def test_whats_new(
    client: TestClient, db: Session, gym_a: GymFixture, platform_admin
) -> None:
    admin = TestClient(client.app)
    sign_in(db, admin, platform_admin)
    draft = admin.post(
        "/api/v1/admin/changelog",
        json={"title": "Visit packs", "body": "Sell 10 visits."},
    ).json()
    sign_in(db, client, gym_a.owner)
    assert client.get("/api/v1/auth/me").json()["changelog_unread"] is False
    assert client.get("/api/v1/changelog").json() == []  # drafts stay ours

    admin.patch(
        f"/api/v1/admin/changelog/{draft['id']}",
        json={"published_at": (utcnow() - dt.timedelta(minutes=1)).isoformat()},
    )
    assert client.get("/api/v1/auth/me").json()["changelog_unread"] is True
    [entry] = client.get("/api/v1/changelog").json()
    assert entry["title"] == "Visit packs"
    assert client.post("/api/v1/changelog/seen").status_code == 204
    assert client.get("/api/v1/auth/me").json()["changelog_unread"] is False
    # Only us: a gym owner can't write one.
    assert (
        client.post(
            "/api/v1/admin/changelog", json={"title": "x", "body": "y"}
        ).status_code
        == 403
    )


def signup(client: TestClient, slug: str, phone: str, ref: str | None):
    return client.post(
        "/api/v1/auth/register-gym",
        json={
            "gym_name": f"Gym {slug}",
            "slug": slug,
            "plan_months": "ad",
            "date_display": "ad",
            "owner_name": "New Owner",
            "owner_phone": phone,
            "password": "correct-horse-battery",
            "accept_terms": True,
            "ref": ref,
        },
    )


def test_a_gym_sends_us_a_gym(
    client: TestClient, db: Session, gym_a: GymFixture, platform_admin
) -> None:
    plan = PlatformPlan(name="Basic", monthly_price=1500_00)
    db.add(plan)
    db.commit()
    sign_in(db, client, gym_a.owner)
    mine = client.get("/api/v1/subscription/referrals").json()
    assert mine["link"].endswith(f"/signup?ref={gym_a.gym.slug}")
    client.headers.pop("Authorization", None)
    client.cookies.clear()

    assert signup(client, "sent-gym", "9841700001", gym_a.gym.slug).status_code == 201
    # A wrong code never stops anyone signing up.
    assert signup(client, "lone-gym", "9841700002", "no-such-gym").status_code == 201
    row = db.scalars(select(GymReferral)).one()
    assert row.status == "pending"

    # Their first payment, approved: ready to reward.
    new_gym = db.scalars(select(Gym).where(Gym.slug == "sent-gym")).one()
    owner_client = TestClient(client.app)
    new_owner = db.scalars(
        select(StaffUser).where(StaffUser.gym_id == new_gym.id)
    ).one()
    sign_in(db, owner_client, new_owner)
    owner_client.post(
        "/api/v1/subscription/payments",
        json={"platform_plan_id": str(plan.id), "months": 1, "amount": 1500_00,
              "transaction_ref": "ES-REF-1"},
    )  # fmt: skip
    admin = TestClient(client.app)
    sign_in(db, admin, platform_admin)
    [pending] = admin.get("/api/v1/admin/subscription-payments").json()
    admin.post(f"/api/v1/admin/subscription-payments/{pending['id']}/approve", json={})
    [ready] = admin.get("/api/v1/admin/gym-referrals?status=ready").json()
    assert (ready["referrer_name"], ready["referred_name"]) == (
        gym_a.gym.name,
        "Gym sent-gym",
    )

    before = {
        g: subscription.state(db, g, count_members=False).ends_on
        for g in (gym_a.gym.id, new_gym.id)
    }
    assert (
        admin.post(f"/api/v1/admin/gym-referrals/{ready['id']}/reward").status_code
        == 204
    )
    for gym_id, ends in before.items():
        after = subscription.state(db, gym_id, count_members=False).ends_on
        assert after > ends  # a month more each
    # Once.
    again = admin.post(f"/api/v1/admin/gym-referrals/{ready['id']}/reward")
    assert again.status_code == 409
    sign_in(db, client, gym_a.owner)
    [mine] = client.get("/api/v1/subscription/referrals").json()["gyms"]
    assert (mine["name"], mine["status"]) == ("Gym sent-gym", "rewarded")
