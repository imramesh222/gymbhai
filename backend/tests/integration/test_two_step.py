"""Two-step sign-in with an authenticator app (PLAN.md §16.1, step 6.3)."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import totp
from app.core.config import settings
from app.core.permissions import Permission
from app.models.staff import StaffUser
from tests.conftest import TEST_PASSWORD, GymFixture, shared_password_hash, sign_in


def code_for(staff: StaffUser, offset: int = 0) -> str:
    secret = totp.secret_for(staff.id, staff.totp_nonce)
    return totp.code_at(secret, totp.step_at() + offset)


def turn_on(client: TestClient, db: Session, staff: StaffUser) -> list[str]:
    """Through the routes, as the person would. Returns the recovery codes."""
    sign_in(db, client, staff)
    setup = client.post("/api/v1/auth/two-step/setup", json={"password": TEST_PASSWORD})
    assert setup.status_code == 200, setup.text
    db.refresh(staff)
    enabled = client.post(
        "/api/v1/auth/two-step/enable", json={"code": code_for(staff)}
    )
    assert enabled.status_code == 200, enabled.text
    db.refresh(staff)
    client.headers.pop("Authorization")
    return enabled.json()["recovery_codes"]


def login(client: TestClient, identifier: str, password: str = TEST_PASSWORD):
    return client.post(
        "/api/v1/auth/login", json={"identifier": identifier, "password": password}
    )


def second_step(client: TestClient, token: str, code: str):
    return client.post(
        "/api/v1/auth/login/two-step", json={"two_step_token": token, "code": code}
    )


# --- turning it on ------------------------------------------------------------------


def test_setting_it_up(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    sign_in(db, client, gym_a.owner)
    wrong = client.post("/api/v1/auth/two-step/setup", json={"password": "nope"})
    assert wrong.status_code == 403
    assert wrong.json()["code"] == "wrong_password"

    setup = client.post("/api/v1/auth/two-step/setup", json={"password": TEST_PASSWORD})
    assert setup.status_code == 200
    body = setup.json()
    assert body["uri"].startswith("otpauth://totp/GymBhai")
    assert body["secret"] in body["uri"]

    db.refresh(gym_a.owner)
    bad = client.post("/api/v1/auth/two-step/enable", json={"code": "000000"})
    assert bad.status_code == 401
    assert not gym_a.owner.two_step_enabled

    good = client.post(
        "/api/v1/auth/two-step/enable", json={"code": code_for(gym_a.owner)}
    )
    assert good.status_code == 200
    codes = good.json()["recovery_codes"]
    assert len(codes) == 10 and len(set(codes)) == 10

    status = client.get("/api/v1/auth/two-step").json()
    assert status == {"enabled": True, "required": False, "recovery_codes_left": 10}
    assert client.get("/api/v1/auth/me").json()["staff"]["two_step_enabled"] is True

    again = client.post("/api/v1/auth/two-step/setup", json={"password": TEST_PASSWORD})
    assert again.status_code == 409


# --- signing in -----------------------------------------------------------------


def test_the_password_alone_is_not_enough(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    turn_on(client, db, gym_a.owner)
    first = login(client, "a@example.com")
    assert first.status_code == 200
    body = first.json()
    assert set(body) == {"two_step_token", "expires_in"}
    assert "gb_refresh" not in first.cookies

    # The setup code's 30-second step is used up; the next one is fresh.
    done = second_step(client, body["two_step_token"], code_for(gym_a.owner, offset=1))
    assert done.status_code == 200, done.text
    assert done.json()["access_token"]
    assert "gb_refresh" in done.cookies


def test_a_code_works_only_once(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    turn_on(client, db, gym_a.owner)
    # The setup code's step is used up; the next one is still fresh.
    code = code_for(gym_a.owner, offset=1)
    token = login(client, "a@example.com").json()["two_step_token"]
    assert second_step(client, token, code).status_code == 200
    token = login(client, "a@example.com").json()["two_step_token"]
    replay = second_step(client, token, code)
    assert replay.status_code == 401
    assert replay.json()["code"] == "bad_code"


def test_a_recovery_code_works_once(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    codes = turn_on(client, db, gym_a.owner)
    token = login(client, "a@example.com").json()["two_step_token"]
    assert second_step(client, token, codes[0].upper()).status_code == 200
    token = login(client, "a@example.com").json()["two_step_token"]
    assert second_step(client, token, codes[0]).status_code == 401

    sign_in(db, client, gym_a.owner)
    assert client.get("/api/v1/auth/two-step").json()["recovery_codes_left"] == 9


def test_wrong_codes_count_towards_the_sign_in_limit(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    turn_on(client, db, gym_a.owner)
    token = login(client, "a@example.com").json()["two_step_token"]
    for _ in range(settings.login_max_failures):
        assert second_step(client, token, "000000").status_code == 401
    locked = second_step(client, token, code_for(gym_a.owner, offset=1))
    assert locked.status_code == 429
    assert login(client, "a@example.com").status_code == 429


def test_a_bad_two_step_token_is_refused(client: TestClient, gym_a: GymFixture) -> None:
    response = second_step(client, "not-a-token", "123456")
    assert response.status_code == 401
    assert response.json()["code"] == "two_step_expired"


def test_a_two_step_token_is_not_a_session(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    turn_on(client, db, gym_a.owner)
    token = login(client, "a@example.com").json()["two_step_token"]
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


# --- recovery codes and turning it off --------------------------------------------


def test_new_recovery_codes_replace_the_old(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    old = turn_on(client, db, gym_a.owner)
    sign_in(db, client, gym_a.owner)
    new = client.post(
        "/api/v1/auth/two-step/recovery-codes", json={"password": TEST_PASSWORD}
    ).json()["recovery_codes"]
    assert set(new).isdisjoint(old)
    client.headers.pop("Authorization")
    token = login(client, "a@example.com").json()["two_step_token"]
    assert second_step(client, token, old[0]).status_code == 401
    assert second_step(client, token, new[0]).status_code == 200


def test_turning_it_off(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    turn_on(client, db, gym_a.owner)
    sign_in(db, client, gym_a.owner)
    wrong = client.post("/api/v1/auth/two-step/disable", json={"password": "nope"})
    assert wrong.status_code == 403
    off = client.post("/api/v1/auth/two-step/disable", json={"password": TEST_PASSWORD})
    assert off.status_code == 204
    client.headers.pop("Authorization")
    assert "access_token" in login(client, "a@example.com").json()


# --- requiring it ---------------------------------------------------------------


def test_the_owner_turns_it_on_for_themselves_first(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    early = client.patch("/api/v1/gym/security", json={"require_two_step": True})
    assert early.status_code == 409
    assert early.json()["code"] == "two_step_owner_first"

    turn_on(client, db, gym_a.owner)
    sign_in(db, client, gym_a.owner)
    response = client.patch("/api/v1/gym/security", json={"require_two_step": True})
    assert response.status_code == 200
    assert response.json()["settings"]["require_two_step"] is True


def test_only_the_owner_can_require_it(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    manager = make_staff(gym_a.gym, permissions=[p.value for p in Permission])
    sign_in(db, client, manager)
    response = client.patch("/api/v1/gym/security", json={"require_two_step": False})
    assert response.status_code == 403
    assert response.json()["code"] == "owner_only"


def test_the_gym_setting_cannot_be_changed_through_gym_settings(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    response = client.patch(
        "/api/v1/gym", json={"settings": {"require_two_step": True}}
    )
    assert response.status_code == 422


def test_staff_who_must_use_it_can_only_set_it_up(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    desk = make_staff(gym_a.gym, permissions=["members.view"])
    turn_on(client, db, gym_a.owner)
    sign_in(db, client, gym_a.owner)
    client.patch("/api/v1/gym/security", json={"require_two_step": True})

    sign_in(db, client, desk)
    blocked = client.get("/api/v1/members")
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "two_step_setup_required"
    me = client.get("/api/v1/auth/me").json()
    assert me["two_step_required"] is True
    assert me["staff"]["two_step_enabled"] is False
    off = client.post("/api/v1/auth/two-step/disable", json={"password": TEST_PASSWORD})
    assert off.status_code == 403

    turn_on(client, db, desk)
    sign_in(db, client, desk)
    assert client.get("/api/v1/members").status_code == 200
    refused = client.post(
        "/api/v1/auth/two-step/disable", json={"password": TEST_PASSWORD}
    )
    assert refused.status_code == 403
    assert refused.json()["code"] == "two_step_required"


def test_platform_admins_must_use_it(client: TestClient, db: Session) -> None:
    admin = StaffUser(
        name="New admin",
        email="new-admin@gymbhai.com",
        password_hash=shared_password_hash(),
        is_platform_admin=True,
    )
    db.add(admin)
    db.commit()
    sign_in(db, client, admin)
    blocked = client.get("/api/v1/admin/gyms")
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "two_step_setup_required"
    assert client.get("/api/v1/auth/me").json()["two_step_required"] is True

    turn_on(client, db, admin)
    sign_in(db, client, admin)
    assert client.get("/api/v1/admin/gyms").status_code == 200


# --- resetting someone else's ---------------------------------------------------


def test_the_owner_resets_a_colleagues(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    desk = make_staff(gym_a.gym, permissions=["members.view"])
    turn_on(client, db, desk)
    sign_in(db, client, gym_a.owner)
    response = client.post(f"/api/v1/staff/{desk.id}/two-step/reset")
    assert response.status_code == 200
    assert response.json()["two_step_enabled"] is False
    assert "access_token" in login(client, desk.phone).json()


def test_nobody_resets_their_own_or_the_owners(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    manager = make_staff(gym_a.gym, permissions=["staff.manage"])
    sign_in(db, client, manager)
    own = client.post(f"/api/v1/staff/{manager.id}/two-step/reset")
    assert own.status_code == 409
    owner = client.post(f"/api/v1/staff/{gym_a.owner.id}/two-step/reset")
    assert owner.status_code == 403
    assert owner.json()["code"] == "owner_protected"


def test_another_gyms_staff_are_not_found(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    gym_b: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    desk = make_staff(gym_a.gym)
    sign_in(db, client, gym_b.owner)
    assert client.post(f"/api/v1/staff/{desk.id}/two-step/reset").status_code == 404


def test_we_reset_an_owners(
    client: TestClient, db: Session, gym_a: GymFixture, platform_admin: StaffUser
) -> None:
    turn_on(client, db, gym_a.owner)
    sign_in(db, client, platform_admin)
    response = client.post(f"/api/v1/admin/gyms/{gym_a.gym.id}/owner-two-step")
    assert response.status_code == 200
    assert response.json()["owner_two_step"] is False
    db.refresh(gym_a.owner)
    assert not gym_a.owner.two_step_enabled
