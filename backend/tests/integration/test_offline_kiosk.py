"""The kiosk keeps working offline (PLAN.md §19.2).

The roster's letters and the kiosk's own rules must reach the same answer as
the server. `test_the_door_cases` builds members in each situation, asks the
server's door (`checkins._decide`) and the roster, and checks both against
shared/src/door/cases.json, which the kiosk's code is tested on too
(frontend/src/lib/doorOffline.test.ts). After changing the door's rules, run
it with UPDATE_DOOR_CASES=1 to write the file again, and read the diff.
"""

import datetime as dt
import hashlib
import json
import os
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import qr
from app.core.time import NEPAL, today_in_nepal, utcnow
from app.models.gym import Branch, Gym
from app.models.member_app import CheckIn, Device
from app.models.plan import Plan
from app.services import checkins, kiosk
from app.services import members as members_service
from app.services import memberships as ms
from tests.conftest import GymFixture, context_for, make_member, sell, sign_in

TODAY = today_in_nepal()
CASES = Path(__file__).resolve().parents[3] / "shared" / "src" / "door" / "cases.json"


def at(time_of_day: str) -> dt.datetime:
    hour, minute = map(int, time_of_day.split(":"))
    return dt.datetime.combine(TODAY, dt.time(hour, minute), tzinfo=NEPAL)


@pytest.fixture
def device(db: Session, gym_a: GymFixture) -> Device:
    row = Device(
        gym_id=gym_a.gym.id, branch_id=gym_a.branch.id, name="Door", token_hash="k" * 64
    )
    db.add(row)
    db.commit()
    return row


# --- the cases both sides agree on -----------------------------------------------


def situations(db: Session, gym: GymFixture) -> dict[str, object]:
    """One member in each situation the door tells apart."""
    ctx = context_for(db, gym.owner)
    n = iter(range(10, 99))

    def member(name: str):
        return make_member(db, gym, name=name, phone=f"98000000{next(n)}")

    def plan(**fields) -> Plan:
        row = Plan(gym_id=gym.gym.id, name=fields.pop("name"), price=1_000_00, **fields)
        db.add(row)
        db.commit()
        return row

    found: dict[str, object] = {}
    found["paid"] = paid = member("Paid")
    sell(db, gym, paid, paid=1_500_00)
    found["owes"] = owes = member("Owes")
    sell(db, gym, owes, paid=500_00)
    found["frozen"] = frozen = member("Frozen")
    held, _ = sell(db, gym, frozen, paid=1_500_00)
    ms.freeze(db, ctx, held, TODAY, TODAY + dt.timedelta(days=2), "away")
    db.commit()
    found["ended_yesterday"] = ended = member("Ended yesterday")
    sell(
        db,
        gym,
        ended,
        paid=1_500_00,
        start_date=TODAY - dt.timedelta(days=30),
        end_date=TODAY - dt.timedelta(days=1),
    )
    found["ended_long_ago"] = long_ago = member("Ended long ago")
    sell(
        db,
        gym,
        long_ago,
        paid=1_500_00,
        start_date=TODAY - dt.timedelta(days=60),
        end_date=TODAY - dt.timedelta(days=31),
    )
    found["starts_next_week"] = later = member("Starts next week")
    sell(db, gym, later, paid=1_500_00, start_date=TODAY + dt.timedelta(days=7))
    elsewhere = Branch(gym_id=gym.gym.id, name="Koteshwor")
    db.add(elsewhere)
    db.commit()
    found["other_branch"] = away = member("Other branch")
    there = plan(name="Koteshwor only", duration_days=30, all_branches=False)
    from app.models.plan import PlanBranch

    db.add(PlanBranch(plan_id=there.id, branch_id=elsewhere.id))
    db.commit()
    sell(db, gym, away, plan=there, paid=1_000_00, branch_id=elsewhere.id)
    found["visits_used"] = used = member("Visits used")
    pack = plan(name="1 visit", duration_days=10, visit_limit=1)
    sell(db, gym, used, plan=pack, paid=1_000_00)
    checkins.check_in(
        db, gym=gym.gym, member=used, branch_id=gym.branch.id, method="manual"
    )
    db.commit()
    found["off_peak"] = morning = member("Off-peak")
    early = plan(
        name="Mornings",
        duration_days=30,
        access_hours=[{"days": [0, 1, 2, 3, 4, 5, 6], "from": "06:00", "to": "10:00"}],
    )
    sell(db, gym, morning, plan=early, paid=1_000_00)
    found["archived"] = gone = member("Archived")
    sell(db, gym, gone, paid=1_500_00)
    gone.is_archived = True
    db.commit()
    return found


# (situation, time of day, dues rule, grace days)
SITUATIONS = [
    ("paid", "08:00", "warn", 0),
    ("owes", "08:00", "allow", 0),
    ("owes", "08:00", "warn", 0),
    ("owes", "08:00", "refuse", 0),
    ("frozen", "08:00", "warn", 0),
    ("ended_yesterday", "08:00", "warn", 3),
    ("ended_yesterday", "08:00", "warn", 0),
    ("ended_long_ago", "08:00", "warn", 3),
    ("starts_next_week", "08:00", "warn", 0),
    ("other_branch", "08:00", "warn", 0),
    ("visits_used", "08:00", "warn", 0),
    ("off_peak", "08:00", "warn", 0),
    ("off_peak", "20:00", "warn", 0),
    ("archived", "08:00", "warn", 0),
]


def test_the_door_cases(db: Session, gym_a: GymFixture, device: Device) -> None:
    found = situations(db, gym_a)
    cases = []
    for name, time_of_day, rule, grace in SITUATIONS:
        gym = db.get(Gym, gym_a.gym.id)
        gym.settings = {**gym.settings, "dues_rule": rule, "grace_days": grace}
        db.commit()
        member = found[name]
        [entry] = [e for e in kiosk.roster(db, device, TODAY) if e.id == member.id]
        result, reason, _ = checkins._decide(
            db, gym, member, gym_a.branch.id, at(time_of_day)
        )
        cases.append(
            {
                "name": f"{name}, {rule}, grace {grace}, at {time_of_day}",
                "days": entry.days,
                "hours": entry.hours,
                "visits_left": entry.visits_left,
                "owes": entry.owes,
                "rules": {
                    "grace_days": grace,
                    "rescan_minutes": 180,
                    "dues_rule": rule,
                },
                "time": time_of_day,
                "expected": {"result": result, "reason": reason},
            }
        )
    if os.environ.get("UPDATE_DOOR_CASES"):
        CASES.write_text(json.dumps(cases, indent=2, ensure_ascii=False) + "\n")
    assert json.loads(CASES.read_text()) == cases, (
        "The door's rules changed: run with UPDATE_DOOR_CASES=1, read the diff of "
        "shared/src/door/cases.json, and run the frontend's doorOffline test."
    )


def test_the_letters_follow_the_days(db: Session, gym_a: GymFixture, device) -> None:
    found = situations(db, gym_a)
    letters = {e.id: e.days for e in kiosk.roster(db, device, TODAY)}
    assert letters[found["paid"].id] == "a" * kiosk.DAYS
    assert letters[found["frozen"].id].startswith("fffa")
    assert letters[found["starts_next_week"].id] == "x" * 7 + "a" * 7
    assert letters[found["other_branch"].id] == "b" * kiosk.DAYS
    assert letters[found["archived"].id] == "x" * kiosk.DAYS


# --- the roster -----------------------------------------------------------------


@pytest.fixture
def kiosk_client(client: TestClient, db: Session, gym_a: GymFixture) -> TestClient:
    sign_in(db, client, gym_a.owner)
    registered = client.post(
        "/api/v1/devices",
        json={"branch_id": str(gym_a.branch.id), "name": "Front door"},
    ).json()
    door = TestClient(client.app)
    door.headers["X-Device-Token"] = registered["token"]
    return door


def test_the_roster_has_what_the_door_needs_and_no_more(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    gym_b: GymFixture,
    kiosk_client: TestClient,
) -> None:
    sita = make_member(db, gym_a)
    sell(db, gym_a, sita, paid=500_00)
    stranger = make_member(db, gym_b, phone="9819999999")
    sell(db, gym_b, stranger)
    client.patch("/api/v1/gym/check-in-rules", json={"kiosk_offline_days": 5})

    roster = kiosk_client.get("/api/v1/kiosk/roster").json()
    assert roster["from_date"] == TODAY.isoformat()
    assert roster["offline_days"] == 5
    assert roster["rules"] == {
        "grace_days": 0,
        "rescan_minutes": 180,
        "dues_rule": "warn",
    }
    [entry] = roster["members"]
    assert entry["name"] == "Sita Rai" and entry["owes"]
    assert entry["key"] == qr.public_key(sita.qr_secret, sita.qr_version)
    assert entry["card"] == hashlib.sha256(sita.card_token.encode()).hexdigest()
    # Nothing a stolen kiosk shouldn't hold.
    assert not {"phone", "email", "notes", "dues"} & set(entry)


def test_a_reader_or_a_revoked_kiosk_gets_no_roster(
    client: TestClient, db: Session, gym_a: GymFixture, kiosk_client: TestClient
) -> None:
    [door] = db.scalars(select(Device)).all()
    door.kind = "hikvision"
    db.commit()
    assert kiosk_client.get("/api/v1/kiosk/roster").json()["code"] == "not_a_kiosk"
    door.kind = "kiosk"
    door.revoked_at = utcnow()
    db.commit()
    assert kiosk_client.get("/api/v1/kiosk/roster").status_code == 401


def test_a_gb2_code_lets_them_in_online_too(
    db: Session, gym_a: GymFixture, kiosk_client: TestClient
) -> None:
    sita = make_member(db, gym_a)
    sell(db, gym_a, sita, paid=1_500_00)
    code = qr.app_code2(
        sita.id,
        qr.signing_key(sita.qr_secret, sita.qr_version),
        qr.window_at(time.time()),
    )
    scanned = kiosk_client.post("/api/v1/kiosk/scan", json={"code": code}).json()
    assert scanned["result"] == "allowed"
    # Signed with someone else's key: not a code of ours.
    forged = qr.app_code2(
        sita.id, qr.signing_key("ab" * 32, 1), qr.window_at(time.time())
    )
    assert (
        kiosk_client.post("/api/v1/kiosk/scan", json={"code": forged}).json()["result"]
        == "unknown"
    )


# --- offline scans, sent later -----------------------------------------------------


def offline(member, *, client_id: str | None = None, minutes_ago: int = 30, **extra):
    return {
        "client_id": client_id or uuid.uuid4().hex,
        "member_id": str(member.id),
        "method": "app_qr",
        "at": (utcnow() - dt.timedelta(minutes=minutes_ago)).isoformat(),
        "result": "allowed",
        **extra,
    }


def test_offline_scans_are_recorded_as_decided_once(
    db: Session, gym_a: GymFixture, kiosk_client: TestClient
) -> None:
    sita = make_member(db, gym_a)
    membership, _ = sell(db, gym_a, sita, paid=1_500_00)
    scans = [
        offline(sita, client_id="scan-0001"),
        offline(sita, client_id="scan-0002", minutes_ago=10, result="duplicate"),
    ]
    sent = kiosk_client.post("/api/v1/kiosk/scans", json={"scans": scans})
    assert sent.json() == {"recorded": 2}
    again = kiosk_client.post("/api/v1/kiosk/scans", json={"scans": scans})
    assert again.json() == {"recorded": 0}
    rows = db.scalars(select(CheckIn).order_by(CheckIn.at)).all()
    assert [(r.result, r.offline, r.membership_id) for r in rows] == [
        ("allowed", True, membership.id),
        ("duplicate", True, membership.id),
    ]


def test_what_a_kiosk_may_not_send_is_skipped(
    db: Session, gym_a: GymFixture, gym_b: GymFixture, kiosk_client: TestClient
) -> None:
    sita = make_member(db, gym_a)
    sell(db, gym_a, sita, paid=1_500_00)
    stranger = make_member(db, gym_b, phone="9819999999")
    scans = [
        offline(stranger),  # another gym's member
        offline(sita, result="override"),  # only staff override
        offline(sita, minutes_ago=-60),  # an hour from now
        offline(sita, minutes_ago=10 * 24 * 60),  # older than it may be offline
    ]
    sent = kiosk_client.post("/api/v1/kiosk/scans", json={"scans": scans})
    assert sent.json() == {"recorded": 0}
    assert not db.scalars(select(CheckIn)).first()


def test_an_offline_visit_counts_against_a_pack(
    db: Session, gym_a: GymFixture, kiosk_client: TestClient
) -> None:
    pack = Plan(
        gym_id=gym_a.gym.id,
        name="2 visits",
        duration_days=10,
        price=500_00,
        visit_limit=2,
    )
    db.add(pack)
    db.commit()
    sita = make_member(db, gym_a)
    sell(db, gym_a, sita, plan=pack, paid=500_00)
    kiosk_client.post("/api/v1/kiosk/scans", json={"scans": [offline(sita)]})
    assert members_service.state(db, sita).visits_left == 1


def test_today_says_when_a_kiosk_went_quiet(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    def kiosk_seen(name: str, minutes_ago: int) -> None:
        db.add(
            Device(
                gym_id=gym_a.gym.id,
                branch_id=gym_a.branch.id,
                name=name,
                token_hash=uuid.uuid4().hex * 2,
                last_seen_at=utcnow() - dt.timedelta(minutes=minutes_ago),
            )
        )

    kiosk_seen("Front door", 60)
    kiosk_seen("Back door", 2)  # just asked for its roster
    kiosk_seen("Old tablet", 3 * 24 * 60)  # switched off for good
    db.commit()
    sign_in(db, client, gym_a.owner)
    quiet = client.get("/api/v1/dashboard/today").json()["quiet_kiosks"]
    assert [k["name"] for k in quiet] == ["Front door"]
