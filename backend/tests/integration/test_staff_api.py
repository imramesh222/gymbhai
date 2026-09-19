from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.gym import Branch
from app.models.staff import StaffSession, StaffUser
from tests.conftest import GymFixture, sign_in


def create(client: TestClient, **fields):
    body = {
        "name": "Hari",
        "phone": "9841111111",
        "password": "front-desk-123",
        **fields,
    }
    return client.post("/api/v1/staff", json=body)


def test_owner_creates_front_desk_staff_from_the_preset(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    catalog = client.get("/api/v1/staff/permissions").json()
    assert len(catalog["permissions"]) == 29
    front_desk = catalog["presets"]["front_desk"]
    response = create(client, permissions=front_desk)
    assert response.status_code == 201, response.text
    assert response.json()["permissions"] == sorted(front_desk)

    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "9841111111", "password": "front-desk-123"},
    )
    assert sorted(login.json()["me"]["permissions"]) == sorted(front_desk)


def test_a_manager_can_only_grant_what_they_hold(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    manager = make_staff(gym_a.gym, permissions=["staff.manage", "members.view"])
    sign_in(db, client, manager)
    assert create(client, permissions=["members.view"]).status_code == 201
    refused = create(client, phone="9841111112", permissions=["payments.void"])
    assert refused.status_code == 403
    assert refused.json()["permissions"] == ["payments.void"]
    refused = create(client, phone="9841111113", permissions=["staff.manage"])
    assert refused.json()["permissions"] == ["staff.manage"]
    assert client.get("/api/v1/staff/permissions").json()["grantable"] == [
        "members.view"
    ]


def test_nobody_edits_the_owner(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    manager = make_staff(gym_a.gym, permissions=["staff.manage"])
    sign_in(db, client, manager)
    response = client.patch(
        f"/api/v1/staff/{gym_a.owner.id}", json={"is_active": False}
    )
    assert response.json()["code"] == "owner_protected"

    sign_in(db, client, gym_a.owner)
    response = client.patch(f"/api/v1/staff/{gym_a.owner.id}", json={"permissions": []})
    assert response.json()["code"] == "owner_protected"
    # The owner may still correct their own name.
    renamed = client.patch(f"/api/v1/staff/{gym_a.owner.id}", json={"name": "Sita S."})
    assert renamed.json()["name"] == "Sita S."


def test_only_the_owner_manages_managers(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    manager = make_staff(gym_a.gym, permissions=["staff.manage"])
    other = make_staff(gym_a.gym, permissions=["staff.manage"])
    sign_in(db, client, manager)
    response = client.patch(f"/api/v1/staff/{other.id}", json={"is_active": False})
    assert response.json()["code"] == "manager_protected"


def test_disabling_signs_out_everywhere(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    staff = make_staff(gym_a.gym)
    sign_in(db, client, staff)
    sign_in(db, client, gym_a.owner)
    assert (
        client.patch(
            f"/api/v1/staff/{gym_a.owner.id}", json={"is_active": False}
        ).json()["code"]
        == "owner_protected"
    )
    client.patch(f"/api/v1/staff/{staff.id}", json={"is_active": False})
    sessions = db.query(StaffSession).filter_by(staff_user_id=staff.id).all()
    assert sessions and all(s.revoked_at is not None for s in sessions)


def test_branch_limits_carry_down(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    other = Branch(gym_id=gym_a.gym.id, name="Koteshwor")
    db.add(other)
    db.commit()
    manager = make_staff(
        gym_a.gym, permissions=["staff.manage"], branches=[gym_a.branch]
    )
    sign_in(db, client, manager)
    # "Every branch" is more than the manager has.
    assert create(client).json()["code"] == "cannot_grant"
    assert create(client, branch_ids=[str(other.id)]).json()["code"] == "cannot_grant"
    made = create(client, branch_ids=[str(gym_a.branch.id)])
    assert made.json()["branch_ids"] == [str(gym_a.branch.id)]


def test_password_reset_and_own_change(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    staff = make_staff(gym_a.gym)
    sign_in(db, client, gym_a.owner)
    response = client.post(
        f"/api/v1/staff/{staff.id}/password", json={"new_password": "brand-new-pass"}
    )
    assert response.status_code == 204

    sign_in(db, client, staff)
    wrong = client.post(
        "/api/v1/auth/password",
        json={"current_password": "nope", "new_password": "another-pass-1"},
    )
    assert wrong.json()["code"] == "wrong_password"
    ok = client.post(
        "/api/v1/auth/password",
        json={"current_password": "brand-new-pass", "new_password": "another-pass-1"},
    )
    assert ok.status_code == 204


def test_cannot_disable_yourself(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    manager = make_staff(gym_a.gym, permissions=["staff.manage"])
    sign_in(db, client, manager)
    response = client.patch(f"/api/v1/staff/{manager.id}", json={"is_active": False})
    # A manager is protected even from themselves; the owner can do it.
    assert response.status_code in (403, 409)
