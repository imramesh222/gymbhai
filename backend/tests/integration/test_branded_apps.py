"""A gym's own app in the stores (PLAN.md §20.3): asked for in Settings,
moved along from /admin, paid for through Subscription, offered to members."""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.branded_app import BrandedApp
from tests.conftest import GymFixture, sign_in


def png(width: int, height: int, mode: str = "RGBA") -> bytes:
    out = io.BytesIO()
    Image.new(mode, (width, height), (200, 30, 30, 128)).save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def admin(client: TestClient, db: Session, platform_admin) -> TestClient:
    admin = TestClient(client.app)
    sign_in(db, admin, platform_admin)
    return admin


@pytest.fixture
def priced(admin: TestClient) -> None:
    set_prices = admin.patch(
        "/api/v1/admin/settings",
        json={
            "branded_app_setup_price": 15000_00,
            "branded_app_monthly_price": 1000_00,
        },
    )
    assert set_prices.status_code == 200, set_prices.text


def test_not_offered_until_we_price_it(
    client: TestClient, db: Session, gym_a: GymFixture, admin: TestClient
) -> None:
    sign_in(db, client, gym_a.owner)
    assert client.get("/api/v1/gym/app").json()["offered"] is False
    refused = client.put("/api/v1/gym/app", json={"app_name": "FZ", "color": "#1d5fd1"})
    assert refused.status_code == 409 and refused.json()["code"] == "app_not_offered"
    # Setting a price leaves WhatsApp's credits as they were.
    before = admin.get("/api/v1/admin/settings").json()["whatsapp_credits"]
    admin.patch("/api/v1/admin/settings", json={"branded_app_setup_price": 1_00})
    assert admin.get("/api/v1/admin/settings").json()["whatsapp_credits"] == before
    assert client.get("/api/v1/gym/app").json()["offered"] is False


def test_ask_change_and_withdraw(
    client: TestClient, db: Session, gym_a: GymFixture, priced
) -> None:
    sign_in(db, client, gym_a.owner)
    asked = client.put(
        "/api/v1/gym/app", json={"app_name": "Fitness Zone", "color": "#1D5FD1"}
    )
    assert asked.status_code == 200, asked.text
    body = asked.json()
    assert (body["status"], body["app_name"], body["color"]) == (
        "asked",
        "Fitness Zone",
        "#1d5fd1",
    )
    assert (body["setup_price"], body["monthly_price"]) == (15000_00, 1000_00)
    row = db.scalars(select(BrandedApp)).one()
    assert row.android_package == "np.gymbhai.fitness_zone"
    assert row.ios_bundle_id == "np.gymbhai.fitness-zone"

    changed = client.put(
        "/api/v1/gym/app", json={"app_name": "FZ Gym", "color": "#000000"}
    )
    assert changed.json()["app_name"] == "FZ Gym"
    assert len(db.scalars(select(BrandedApp)).all()) == 1

    withdrawn = client.post("/api/v1/gym/app/withdraw")
    assert withdrawn.json()["status"] == "stopped"
    # Asked again, it's the same row.
    again = client.put(
        "/api/v1/gym/app", json={"app_name": "FZ Gym", "color": "#000000"}
    )
    assert again.json()["status"] == "asked"


def test_the_icon_is_square_and_large(
    client: TestClient, db: Session, gym_a: GymFixture, priced
) -> None:
    sign_in(db, client, gym_a.owner)
    client.put("/api/v1/gym/app", json={"app_name": "Fitness Zone", "color": "#1d5fd1"})
    small = client.post(
        "/api/v1/gym/app/icon", files={"file": ("i.png", png(512, 512), "image/png")}
    )
    assert small.status_code == 422 and small.json()["code"] == "bad_icon"
    wide = client.post(
        "/api/v1/gym/app/icon", files={"file": ("i.png", png(1400, 1024), "image/png")}
    )
    assert wide.status_code == 422
    junk = client.post(
        "/api/v1/gym/app/icon", files={"file": ("i.png", b"not an image", "image/png")}
    )
    assert junk.status_code == 422
    good = client.post(
        "/api/v1/gym/app/icon", files={"file": ("i.png", png(2048, 2048), "image/png")}
    )
    assert good.status_code == 200, good.text
    assert good.json()["icon_url"]
    from app.services import storage

    row = db.scalars(select(BrandedApp)).one()
    db.refresh(row)
    kept = Image.open(io.BytesIO(storage.read(row.icon_key or "") or b""))
    # 1024, flat: the App Store refuses an icon with any transparency.
    assert (kept.size, kept.mode) == ((1024, 1024), "RGB")


def test_from_asked_to_live(
    client: TestClient, db: Session, gym_a: GymFixture, admin: TestClient, priced
) -> None:
    sign_in(db, client, gym_a.owner)
    client.put("/api/v1/gym/app", json={"app_name": "Fitness Zone", "color": "#1d5fd1"})
    [listed] = admin.get("/api/v1/admin/apps").json()
    assert (listed["gym_slug"], listed["status"]) == ("fitness-zone", "asked")
    app_id = listed["id"]

    # The setup fee is owed; the monthly add-on not yet.
    overview = client.get("/api/v1/subscription").json()
    assert (overview["app_setup_due"], overview["app_monthly"]) == (15000_00, None)

    building = admin.patch(
        f"/api/v1/admin/apps/{app_id}",
        json={"status": "building", "expo_project_id": "abc-123"},
    ).json()
    assert building["building_at"] is not None
    assert client.get("/api/v1/subscription").json()["app_monthly"] == 1000_00
    # Too late for the gym to change it, or for us to change the ids.
    late = client.put("/api/v1/gym/app", json={"app_name": "Other", "color": "#000000"})
    assert late.status_code == 409 and late.json()["code"] == "app_started"
    fixed = admin.patch(
        f"/api/v1/admin/apps/{app_id}", json={"android_package": "np.other.app"}
    )
    assert fixed.status_code == 409 and fixed.json()["code"] == "app_ids_fixed"

    build = admin.get(f"/api/v1/admin/apps/{app_id}/build").json()
    assert build == {
        "gym": "fitness-zone",
        "name": "Fitness Zone",
        "color": "#1d5fd1",
        "android_package": "np.gymbhai.fitness_zone",
        "ios_bundle_id": "np.gymbhai.fitness-zone",
        "scheme": "gb-fitness-zone",
        "expo_project_id": "abc-123",
        "api_url": "http://localhost:3000",
        "icon_url": None,
    }

    # Members are offered it only once it's live.
    assert client.get("/api/v1/m/fitness-zone/gym").json()["app"] is None
    admin.patch(
        f"/api/v1/admin/apps/{app_id}",
        json={
            "status": "live",
            "play_url": "https://play.google.com/store/apps/details?id=np.gymbhai.fitness_zone",
        },
    )
    offered = client.get("/api/v1/m/fitness-zone/gym").json()["app"]
    assert offered["name"] == "Fitness Zone" and offered["play_url"].startswith(
        "https://play.google.com"
    )

    # The setup fee, paid and approved.
    sent = client.post(
        "/api/v1/subscription/payments",
        json={"kind": "app", "amount": 15000_00, "transaction_ref": "ESW-APP-1"},
    )
    assert sent.status_code == 201, sent.text
    [pending] = admin.get("/api/v1/admin/subscription-payments").json()
    approved = admin.post(
        f"/api/v1/admin/subscription-payments/{pending['id']}/approve", json={}
    )
    assert approved.status_code == 200, approved.text
    assert client.get("/api/v1/gym/app").json()["setup_paid"] is True
    assert client.get("/api/v1/subscription").json()["app_setup_due"] is None
    nothing = client.post(
        "/api/v1/subscription/payments",
        json={"kind": "app", "amount": 15000_00, "transaction_ref": "ESW-APP-2"},
    )
    assert nothing.status_code == 409 and nothing.json()["code"] == "no_app_due"

    admin.patch(f"/api/v1/admin/apps/{app_id}", json={"status": "stopped"})
    assert client.get("/api/v1/subscription").json()["app_monthly"] is None
    assert client.get("/api/v1/m/fitness-zone/gym").json()["app"] is None


def test_each_gym_sees_only_its_own(
    client: TestClient, db: Session, gym_a: GymFixture, gym_b: GymFixture, priced
) -> None:
    sign_in(db, client, gym_a.owner)
    client.put("/api/v1/gym/app", json={"app_name": "Fitness Zone", "color": "#1d5fd1"})
    sign_in(db, client, gym_b.owner)
    assert client.get("/api/v1/gym/app").json()["status"] is None
    assert client.post("/api/v1/gym/app/withdraw").status_code == 404
    # Gym staff never reach /admin's list.
    assert client.get("/api/v1/admin/apps").status_code == 403
