from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.gym import Branch
from app.models.staff import StaffUser
from tests.conftest import GymFixture, sign_in


def test_owner_sees_every_branch(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    db.add(Branch(gym_id=gym_a.gym.id, name="Koteshwor"))
    db.commit()
    sign_in(db, client, gym_a.owner)
    names = [b["name"] for b in client.get("/api/v1/branches").json()]
    assert sorted(names) == ["Koteshwor", "Main branch"]


def test_staff_limited_to_a_branch_see_only_that_branch(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    other = Branch(gym_id=gym_a.gym.id, name="Koteshwor")
    db.add(other)
    db.commit()
    staff = make_staff(gym_a.gym, branches=[other])
    sign_in(db, client, staff)

    assert [b["name"] for b in client.get("/api/v1/branches").json()] == ["Koteshwor"]
    assert client.get(f"/api/v1/branches/{other.id}").status_code == 200
    # A branch of their own gym they were not given looks like it does not exist.
    assert client.get(f"/api/v1/branches/{gym_a.branch.id}").status_code == 404


def test_staff_with_no_branch_rows_work_everywhere(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    sign_in(db, client, make_staff(gym_a.gym))
    assert len(client.get("/api/v1/branches").json()) == 1
