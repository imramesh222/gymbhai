from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services import member_auth
from tests.conftest import TEST_PASSWORD, GymFixture, make_member, sign_in


def admin_client(client: TestClient, db: Session, platform_admin) -> TestClient:
    admin = TestClient(client.app)
    sign_in(db, admin, platform_admin)
    return admin


def test_every_gym_at_a_glance(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    gym_b: GymFixture,
    platform_admin,
) -> None:
    admin = admin_client(client, db, platform_admin)
    gyms = admin.get("/api/v1/admin/gyms").json()
    assert {g["slug"] for g in gyms} == {"fitness-zone", "iron-house"}
    fz = next(g for g in gyms if g["slug"] == "fitness-zone")
    assert fz["subscription_status"] == "trial" and fz["sms_balance"] == 50
    assert fz["owner_phone"] == "9841000001"


def test_gym_staff_cannot_reach_admin(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    response = client.get("/api/v1/admin/gyms")
    assert response.status_code == 403
    assert response.json()["code"] == "platform_admin_only"


def test_prices_are_edited_here(
    client: TestClient, db: Session, platform_admin
) -> None:
    admin = admin_client(client, db, platform_admin)
    plan = admin.post(
        "/api/v1/admin/plans",
        json={"name": "Starter", "max_active_members": 150, "monthly_price": 1500_00},
    ).json()
    updated = admin.patch(
        f"/api/v1/admin/plans/{plan['id']}", json={"monthly_price": 1800_00}
    )
    assert updated.json()["monthly_price"] == 1800_00


def test_credits_and_grants(
    client: TestClient, db: Session, gym_a: GymFixture, platform_admin
) -> None:
    admin = admin_client(client, db, platform_admin)
    gid = gym_a.gym.id
    after = admin.post(
        f"/api/v1/admin/gyms/{gid}/sms-credits", json={"credits": 500, "reason": "cash"}
    ).json()
    assert after["sms_balance"] == 550
    granted = admin.post(
        f"/api/v1/admin/gyms/{gid}/subscription", json={"months": 1}
    ).json()
    assert granted["subscription_status"] == "active"


def test_suspending_stops_staff_members_and_door(
    client: TestClient, db: Session, gym_a: GymFixture, platform_admin
) -> None:
    member = make_member(db, gym_a)
    staff = TestClient(client.app)
    sign_in(db, staff, gym_a.owner)
    admin = admin_client(client, db, platform_admin)
    admin.post(f"/api/v1/admin/gyms/{gym_a.gym.id}/suspend", json={"reason": "abuse"})

    assert staff.get("/api/v1/members").json()["code"] == "gym_suspended"
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "a@example.com", "password": TEST_PASSWORD},
    )
    assert login.json()["code"] == "gym_suspended"
    assert client.get("/api/v1/m/fitness-zone/gym").status_code == 404

    admin.post(f"/api/v1/admin/gyms/{gym_a.gym.id}/unsuspend")
    assert staff.get("/api/v1/members").status_code == 200
    assert member_auth.members_at(
        db, gym_a.gym, member_auth.destination(member.phone, None)
    )


def test_reset_a_locked_out_owner(
    client: TestClient, db: Session, gym_a: GymFixture, platform_admin
) -> None:
    admin = admin_client(client, db, platform_admin)
    response = admin.post(
        f"/api/v1/admin/gyms/{gym_a.gym.id}/owner-password",
        json={"new_password": "a-brand-new-one"},
    )
    assert response.status_code == 204
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "a@example.com", "password": "a-brand-new-one"},
    )
    assert login.status_code == 200
