from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import GymFixture, make_member, sign_in


def test_four_plans_are_seeded_without_prices(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    plans = client.get("/api/v1/plans").json()
    assert [(p["name"], p["duration_months"], p["price"]) for p in plans] == [
        ("1 month", 1, None),
        ("3 months", 3, None),
        ("6 months", 6, None),
        ("1 year", 12, None),
    ]


def test_add_a_branch_limited_plan(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    branch = client.post("/api/v1/branches", json={"name": "Koteshwor"}).json()
    assert (
        client.post("/api/v1/branches", json={"name": "Koteshwor"}).status_code == 409
    )
    response = client.post(
        "/api/v1/plans",
        json={
            "name": "Morning only — 3 months",
            "duration_months": 3,
            "price": 3000_00,
            "all_branches": False,
            "branch_ids": [branch["id"]],
        },
    )
    assert response.status_code == 201, response.text
    plan = response.json()

    member = make_member(db, gym_a)
    sold = client.post(
        f"/api/v1/members/{member.id}/memberships", json={"plan_id": plan["id"]}
    )
    assert sold.json()["code"] == "plan_not_at_branch"
    sold = client.post(
        f"/api/v1/members/{member.id}/memberships",
        json={"plan_id": plan["id"], "branch_id": branch["id"]},
    )
    assert sold.status_code == 201


def test_hide_a_plan(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    sign_in(db, client, gym_a.owner)
    plan = client.get("/api/v1/plans").json()[0]
    client.patch(f"/api/v1/plans/{plan['id']}", json={"is_active": False})
    assert len(client.get("/api/v1/plans").json()) == 3
    assert len(client.get("/api/v1/plans?include_hidden=true").json()) == 4


def test_a_plan_needs_one_duration(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    both = client.post(
        "/api/v1/plans", json={"name": "x", "duration_months": 1, "duration_days": 10}
    )
    assert both.status_code == 422
    days = client.post("/api/v1/plans", json={"name": "Day pass", "duration_days": 1})
    assert days.status_code == 201


def test_last_open_branch_cannot_close(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    response = client.patch(
        f"/api/v1/branches/{gym_a.branch.id}", json={"is_active": False}
    )
    assert response.json()["code"] == "last_branch"


def test_payment_methods_with_qr(
    client: TestClient, db: Session, gym_a: GymFixture, tmp_path, monkeypatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "media_root", str(tmp_path))
    sign_in(db, client, gym_a.owner)
    method = client.post(
        "/api/v1/payment-methods",
        json={"kind": "esewa", "label": "eSewa", "account_number": "9841000001"},
    ).json()
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 64
    updated = client.post(
        f"/api/v1/payment-methods/{method['id']}/qr",
        files={"file": ("qr.png", png, "image/png")},
    ).json()
    assert client.get(updated["qr_image_url"]).content == png

    client.patch(f"/api/v1/payment-methods/{method['id']}", json={"is_active": False})
    assert client.get("/api/v1/payment-methods").json() == []
