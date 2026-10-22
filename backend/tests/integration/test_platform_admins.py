"""The super admin adds the other platform admins and ticks what each may do
(PLAN.md §7 /admin, app/core/admin_permissions.py)."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.activity import ActivityLog
from app.models.staff import StaffSession, StaffUser
from tests.conftest import GymFixture, sign_in

PASSWORD = "a-long-admin-password"


def as_admin(client: TestClient, db: Session, admin: StaffUser) -> TestClient:
    other = TestClient(client.app)
    sign_in(db, other, admin)
    return other


def add_admin(
    client: TestClient, db: Session, super_admin: StaffUser, permissions: list[str]
) -> StaffUser:
    """Added by the super admin, then signed in with two-step sign-in on."""
    response = as_admin(client, db, super_admin).post(
        "/api/v1/admin/admins",
        json={
            "name": "Sita",
            "email": "sita@gymbhai.com",
            "password": PASSWORD,
            "permissions": permissions,
        },
    )
    assert response.status_code == 201, response.text
    admin = db.get(StaffUser, response.json()["id"])
    assert admin is not None
    admin.totp_nonce = "test-nonce"
    admin.totp_enabled_at = utcnow()
    db.commit()
    return admin


def test_the_super_admin_has_everything(
    client: TestClient, db: Session, platform_admin: StaffUser
) -> None:
    me = as_admin(client, db, platform_admin).get("/api/v1/auth/me").json()
    assert me["staff"]["is_super_admin"] is True
    assert set(me["permissions"]) == {
        "admin.admins",
        "admin.apps",
        "admin.billing",
        "admin.changelog",
        "admin.gym_accounts",
        "admin.pricing",
    }


def test_an_admin_does_only_what_was_ticked(
    client: TestClient, db: Session, gym_a: GymFixture, platform_admin: StaffUser
) -> None:
    billing = add_admin(client, db, platform_admin, ["admin.billing"])
    api = as_admin(client, db, billing)
    assert api.get("/api/v1/auth/me").json()["permissions"] == ["admin.billing"]

    # Every admin sees the gyms and our plans.
    assert api.get("/api/v1/admin/gyms").status_code == 200
    assert api.get("/api/v1/admin/plans").status_code == 200
    gid = gym_a.gym.id
    assert (
        api.post(
            f"/api/v1/admin/gyms/{gid}/sms-credits",
            json={"credits": 100, "reason": "cash"},
        ).status_code
        == 200
    )

    refused = [
        api.post(f"/api/v1/admin/gyms/{gid}/suspend", json={"reason": "spam"}),
        api.post("/api/v1/admin/plans", json={"name": "Starter"}),
        api.get("/api/v1/admin/changelog"),
        api.get("/api/v1/admin/apps"),
        api.get("/api/v1/admin/admins"),
    ]
    for response in refused:
        assert response.status_code == 403, response.request.url
        assert response.json()["code"] == "admin_permission_denied"


def test_only_the_super_admin_adds_admins_and_never_another_super_admin(
    client: TestClient, db: Session, gym_a: GymFixture, platform_admin: StaffUser
) -> None:
    owner = as_admin(client, db, gym_a.owner)
    for response in (
        owner.get("/api/v1/admin/admins"),
        owner.patch(f"/api/v1/admin/admins/{platform_admin.id}", json={"name": "Me"}),
    ):
        assert response.status_code == 403
        assert response.json()["code"] == "platform_admin_only"

    api = as_admin(client, db, platform_admin)
    refused = api.post(
        "/api/v1/admin/admins",
        json={
            "name": "Hari",
            "email": "hari@gymbhai.com",
            "password": PASSWORD,
            "permissions": ["admin.admins"],
        },
    )
    assert refused.status_code == 422
    assert refused.json()["code"] == "bad_permission"

    short = api.post(
        "/api/v1/admin/admins",
        json={"name": "Hari", "email": "hari@gymbhai.com", "password": "short-pass1"},
    )
    assert short.status_code == 422

    taken = api.post(
        "/api/v1/admin/admins",
        json={"name": "Hari", "email": "admin@gymbhai.com", "password": PASSWORD},
    )
    assert taken.status_code == 409

    # Nor can anyone in /admin change the super admin.
    response = api.patch(
        f"/api/v1/admin/admins/{platform_admin.id}", json={"is_active": False}
    )
    assert response.status_code == 403
    assert response.json()["code"] == "super_admin_protected"


def test_changing_an_admin_is_logged_and_turning_off_signs_them_out(
    client: TestClient, db: Session, platform_admin: StaffUser
) -> None:
    sita = add_admin(client, db, platform_admin, ["admin.billing"])
    sita_api = as_admin(client, db, sita)
    api = as_admin(client, db, platform_admin)

    changed = api.patch(
        f"/api/v1/admin/admins/{sita.id}",
        json={"permissions": ["admin.pricing", "admin.changelog"]},
    ).json()
    assert changed["permissions"] == ["admin.changelog", "admin.pricing"]
    assert sita_api.get("/api/v1/admin/changelog").status_code == 200

    listed = api.get("/api/v1/admin/admins").json()
    assert [(a["name"], a["is_super_admin"]) for a in listed] == [
        ("GymBhai admin", True),
        ("Sita", False),
    ]

    assert (
        api.patch(f"/api/v1/admin/admins/{sita.id}", json={"is_active": False}).json()[
            "is_active"
        ]
        is False
    )
    assert sita_api.get("/api/v1/admin/gyms").status_code == 401
    live = db.scalars(
        select(StaffSession).where(
            StaffSession.staff_user_id == sita.id, StaffSession.revoked_at.is_(None)
        )
    ).all()
    assert live == []

    actions = db.scalars(
        select(ActivityLog.action)
        .where(ActivityLog.entity_id == sita.id)
        .order_by(ActivityLog.at)
    ).all()
    assert actions == ["admin.created", "admin.updated", "admin.updated"]


def test_a_lost_phone_or_password(
    client: TestClient, db: Session, platform_admin: StaffUser
) -> None:
    sita = add_admin(client, db, platform_admin, [])
    api = as_admin(client, db, platform_admin)
    reset = api.post(f"/api/v1/admin/admins/{sita.id}/two-step/reset").json()
    assert reset["two_step_enabled"] is False
    assert (
        api.post(
            f"/api/v1/admin/admins/{sita.id}/password",
            json={"new_password": "another-long-password"},
        ).status_code
        == 204
    )
