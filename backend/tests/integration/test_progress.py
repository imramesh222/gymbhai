"""Progress (PLAN.md §19.5): weight and measurements, and photos private to
the member unless shared with their trainer."""

import datetime as dt
import io

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import today_in_nepal
from app.models.activity import ActivityLog
from app.models.progress import ProgressEntry, ProgressPhoto
from app.models.training import PtPackage, PtPlan
from app.services import member_auth, storage
from tests.conftest import GymFixture, make_member, sign_in

TODAY = today_in_nepal()


def app_for(client: TestClient, db: Session, member) -> TestClient:
    issued = member_auth.start_session(db, member, None)
    db.commit()
    app = TestClient(client.app)
    app.headers["Authorization"] = f"Bearer {issued.access_token}"
    return app


def phone_photo(width: int = 3000, height: int = 4000) -> bytes:
    """A big JPEG with a location in it, as a phone takes one."""
    image = Image.new("RGB", (width, height), (200, 120, 80))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # Make
    gps = {1: "N", 2: (27.0, 42.0, 0.0), 3: "E", 4: (85.0, 19.0, 0.0)}
    exif[0x8825] = gps  # GPSInfo
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif.tobytes(), quality=60)
    return out.getvalue()


def test_the_member_records_their_own(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sita = make_member(db, gym_a)
    app = app_for(client, db, sita)
    saved = app.post("/api/v1/m/progress", json={"weight_g": 62_500, "waist_mm": 760})
    assert saved.status_code == 201, saved.text
    [entry] = saved.json()["entries"]
    assert entry["measured_on"] == TODAY.isoformat()
    assert (entry["weight_g"], entry["recorded_by_name"]) == (62_500, None)

    empty = app.post("/api/v1/m/progress", json={"note": "felt good"})
    assert empty.status_code == 422
    later = (TODAY + dt.timedelta(days=1)).isoformat()
    future = app.post(
        "/api/v1/m/progress", json={"weight_g": 62_000, "measured_on": later}
    )
    assert future.json()["code"] == "future_date"

    height = app.put("/api/v1/m/progress/height", json={"height_mm": 1620})
    assert height.json()["height_mm"] == 1620


def test_the_log_says_what_was_done_never_the_figures(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sita = make_member(db, gym_a)
    app_for(client, db, sita).post("/api/v1/m/progress", json={"weight_g": 62_500})
    [logged] = db.scalars(
        select(ActivityLog).where(ActivityLog.action == "progress.recorded")
    )
    assert "62500" not in str(logged.changes)


def test_staff_record_and_change_only_what_staff_recorded(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
) -> None:
    sita = make_member(db, gym_a)
    app = app_for(client, db, sita)
    mine = app.post("/api/v1/m/progress", json={"weight_g": 62_500}).json()
    trainer = make_staff(gym_a.gym, permissions=["progress.record", "members.view"])
    sign_in(db, client, trainer)
    theirs = client.post(
        f"/api/v1/members/{sita.id}/progress",
        json={"weight_g": 62_000, "chest_mm": 900},
    )
    assert theirs.status_code == 201, theirs.text
    by_staff = next(e for e in theirs.json()["entries"] if e["recorded_by_name"])
    assert by_staff["recorded_by_name"] == trainer.name

    refused = client.patch(
        f"/api/v1/progress/{mine['entries'][0]['id']}", json={"weight_g": 70_000}
    )
    assert refused.json()["code"] == "members_own"
    changed = client.patch(
        f"/api/v1/progress/{by_staff['id']}", json={"weight_g": 61_900}
    )
    assert changed.status_code == 200
    # The member may change or delete any of theirs, staff's too.
    deleted = app.delete(f"/api/v1/m/progress/{by_staff['id']}")
    assert len(deleted.json()["entries"]) == 1


def test_staff_need_the_permission(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
) -> None:
    sita = make_member(db, gym_a)
    sign_in(db, client, make_staff(gym_a.gym, permissions=["members.view"]))
    assert client.get(f"/api/v1/members/{sita.id}/progress").status_code == 403


def test_photos_are_shrunk_and_lose_their_location(
    client: TestClient, db: Session, gym_a: GymFixture, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(storage.settings, "media_root", str(tmp_path))
    sita = make_member(db, gym_a)
    app = app_for(client, db, sita)
    sent = app.post(
        "/api/v1/m/progress/photos",
        data={"pose": "front"},
        files={"file": ("me.jpg", phone_photo(), "image/jpeg")},
    )
    assert sent.status_code == 201, sent.text
    [photo] = db.scalars(select(ProgressPhoto))
    kept = Image.open(io.BytesIO(storage.read(photo.photo_key)))
    assert max(kept.size) == 1600
    assert not kept.getexif()  # no location, no camera


def test_photos_are_private_unless_shared_with_their_trainer(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff,
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(storage.settings, "media_root", str(tmp_path))
    sita = make_member(db, gym_a)
    app = app_for(client, db, sita)
    for pose in ("front", "side"):
        app.post(
            "/api/v1/m/progress/photos",
            data={"pose": pose},
            files={"file": ("me.jpg", phone_photo(400, 600), "image/jpeg")},
        )
    front = db.scalars(select(ProgressPhoto).where(ProgressPhoto.pose == "front")).one()
    app.patch(f"/api/v1/m/progress/photos/{front.id}", json={"shared": True})

    trainer = make_staff(gym_a.gym, permissions=["progress.record", "pt.train"])
    other = make_staff(gym_a.gym, permissions=["progress.record"])
    plan = PtPlan(
        gym_id=gym_a.gym.id,
        name="Monthly PT",
        kind="monthly",
        duration_months=1,
        price=8_000_00,
    )
    db.add(plan)
    db.flush()
    db.add(
        PtPackage(
            gym_id=gym_a.gym.id,
            member_id=sita.id,
            plan_id=plan.id,
            plan_name=plan.name,
            kind="monthly",
            trainer_id=trainer.id,
            branch_id=gym_a.branch.id,
            start_date=TODAY,
            end_date=TODAY + dt.timedelta(days=29),
            price=8_000_00,
            discount=0,
        )
    )
    db.commit()

    def photos_seen_by(staff) -> list[str]:
        sign_in(db, client, staff)
        return [
            p["pose"]
            for p in client.get(f"/api/v1/members/{sita.id}/progress").json()["photos"]
        ]

    assert photos_seen_by(trainer) == ["front"]
    assert photos_seen_by(other) == []
    assert photos_seen_by(gym_a.owner) == []  # not even the owner
    assert len(app.get("/api/v1/m/progress").json()["photos"]) == 2


def test_erasing_the_member_takes_it_all(
    client: TestClient, db: Session, gym_a: GymFixture, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(storage.settings, "media_root", str(tmp_path))
    sita = make_member(db, gym_a)
    app = app_for(client, db, sita)
    app.post("/api/v1/m/progress", json={"weight_g": 62_500})
    app.post(
        "/api/v1/m/progress/photos",
        data={"pose": "back"},
        files={"file": ("me.jpg", phone_photo(400, 600), "image/jpeg")},
    )
    key = db.scalars(select(ProgressPhoto.photo_key)).one()
    sign_in(db, client, gym_a.owner)
    assert client.post(f"/api/v1/members/{sita.id}/erase").status_code == 200
    assert not db.scalars(select(ProgressEntry)).first()
    assert not db.scalars(select(ProgressPhoto)).first()
    assert storage.read(key) is None


def test_the_check_up_reminder_goes_by_push_only(
    db: Session, gym_a: GymFixture
) -> None:
    """Off to start; on, it reaches members whose phone takes push, N days
    after their last check, once per check, and never as an SMS (§19.5)."""
    from app.models.job import Job
    from app.models.messaging import ReminderRule, SmsMessage
    from app.services import reminders
    from app.services.push import service as push

    rule = db.scalars(
        select(ReminderRule).where(
            ReminderRule.gym_id == gym_a.gym.id, ReminderRule.trigger == "progress"
        )
    ).one()
    assert (rule.enabled, rule.days) == (False, 30)
    rule.enabled = True

    def member(phone: str, *, last_check_days_ago: int, phone_takes_push: bool):
        m = make_member(db, gym_a, name=f"Member {phone[-2:]}", phone=phone)
        db.add(
            ProgressEntry(
                gym_id=gym_a.gym.id,
                member_id=m.id,
                measured_on=TODAY - dt.timedelta(days=last_check_days_ago),
                weight_g=70_000,
            )
        )
        if phone_takes_push:
            push.subscribe_app(
                db, m, expo_token=f"ExponentPushToken[{phone}]", user_agent="app"
            )
        db.commit()
        return m

    due = member("9812000031", last_check_days_ago=30, phone_takes_push=True)
    member("9812000032", last_check_days_ago=30, phone_takes_push=False)
    member("9812000033", last_check_days_ago=10, phone_takes_push=True)

    assert reminders.run_daily(db) == 1
    db.commit()
    [job] = db.scalars(select(Job).where(Job.kind == push.JOB_PUSH))
    assert job.payload["member_id"] == str(due.id)
    assert job.payload["url"].endswith("/progress")
    assert "30 days" in job.payload["body"]
    assert job.payload["fallback"] is None  # never an SMS instead
    assert not db.scalars(
        select(SmsMessage).where(SmsMessage.kind == "reminder")
    ).first()
    assert reminders.run_daily(db) == 0  # once per check
