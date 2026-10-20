"""Fingerprint and face readers (PLAN.md §18.2): who goes on each reader, the
ZKTeco reader's own protocol (ADMS), the Hikvision reader's bridge, and scans
becoming check-ins under the same rules as a QR scan."""

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import NEPAL, today_in_nepal, utcnow
from app.models.gym import Branch
from app.models.member_app import (
    ALLOWED,
    DENIED_EXPIRED,
    METHOD_FACE,
    METHOD_FINGERPRINT,
    CheckIn,
    Device,
    ReaderUser,
)
from app.models.plan import Plan, PlanBranch
from app.services import memberships as ms
from app.services import readers
from tests.conftest import GymFixture, context_for, make_member, sell, sign_in

TODAY = today_in_nepal()
SERIAL = "CQZ7224160142"


def add_reader(client: TestClient, gym: GymFixture, kind="zkteco", **extra) -> dict:
    body = {"kind": kind, "name": "Front door", "branch_id": str(gym.branch.id)}
    if kind == "zkteco":
        body["serial"] = SERIAL
    response = client.post("/api/v1/devices/readers", json={**body, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def backdate(db: Session, device_id) -> Device:
    """Added yesterday: today's scans come after it."""
    device = db.get(Device, device_id)
    device.created_at = utcnow() - dt.timedelta(days=1)
    db.commit()
    return device


def zk(client: TestClient, path: str, body: str | None = None, **params):
    params = {"SN": SERIAL, **params}
    if body is None:
        return client.get(f"/iclock/{path}", params=params)
    return client.post(f"/iclock/{path}", params=params, content=body)


def scan_line(pin: str, when: dt.datetime, verify: int = 1) -> str:
    return f"{pin}\t{when.astimezone(NEPAL):%Y-%m-%d %H:%M:%S}\t0\t{verify}\t0\t0\t0"


def a_little_ago(minutes: int = 5) -> dt.datetime:
    return (utcnow() - dt.timedelta(minutes=minutes)).replace(microsecond=0)


# --- adding readers -------------------------------------------------------------------


def test_adding_a_reader_of_either_brand(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
):
    sign_in(db, client, gym_a.owner)
    zkteco = add_reader(client, gym_a)
    assert zkteco["device"]["kind"] == "zkteco"
    assert zkteco["device"]["serial"] == SERIAL
    hikvision = add_reader(client, gym_a, kind="hikvision", name="Side door")
    assert hikvision["token"]
    listed = {d["kind"]: d for d in client.get("/api/v1/devices").json()}
    assert (listed["zkteco"]["on_reader"], listed["zkteco"]["waiting"]) == (0, 0)

    again = client.post(
        "/api/v1/devices/readers",
        json={
            "kind": "zkteco",
            "name": "Again",
            "branch_id": str(gym_a.branch.id),
            "serial": SERIAL.lower(),
        },
    )
    assert (again.status_code, again.json()["code"]) == (409, "serial_taken")
    nameless = client.post(
        "/api/v1/devices/readers",
        json={"kind": "zkteco", "name": "X", "branch_id": str(gym_a.branch.id)},
    )
    assert nameless.status_code == 422

    sign_in(db, client, make_staff(gym_a.gym, permissions=["door.check_in"]))
    refused = client.post(
        "/api/v1/devices/readers",
        json={"kind": "hikvision", "name": "X", "branch_id": str(gym_a.branch.id)},
    )
    assert refused.json()["permission"] == "setup.devices"


# --- ZKTeco, over ADMS ---------------------------------------------------------------


def test_a_zkteco_reader_starts_and_takes_its_members(
    client: TestClient, db: Session, gym_a: GymFixture
):
    sita = make_member(db, gym_a)
    sell(db, gym_a, sita, paid=1500_00)
    sign_in(db, client, gym_a.owner)
    add_reader(client, gym_a)

    options = zk(client, "cdata", options="all", pushver="2.4.1")
    assert options.status_code == 200
    assert options.text.startswith(f"GET OPTION FROM: {SERIAL}\n")
    assert "Realtime=1" in options.text
    assert zk(client, "cdata", SN="NOT-OURS").status_code == 404

    waiting = zk(client, "getrequest").text.strip().splitlines()
    pin = readers.pin_of(sita)
    assert waiting == [
        f"C:1:DATA UPDATE USERINFO PIN={pin}\tName=Sita Rai\tPri=0\tPasswd=\tCard="
        "\tGrp=1\tTZ=0000000100000000\tVerify=0"
    ]
    # Not answered yet: not sent again at once.
    assert zk(client, "getrequest").text == "OK"
    assert zk(client, "devicecmd", "ID=1&Return=0&CMD=DATA\n").text == "OK"
    row = db.scalars(select(ReaderUser)).one()
    db.refresh(row)
    assert row.done_at is not None and row.on_reader


def test_scans_become_check_ins_under_the_same_rules(
    client: TestClient, db: Session, gym_a: GymFixture
):
    sita = make_member(db, gym_a)
    sell(db, gym_a, sita, paid=1500_00)
    ram = make_member(db, gym_a, name="Ram Thapa", phone="9812345679")
    sell(db, gym_a, ram, paid=1500_00, start_date=TODAY - dt.timedelta(days=40),
         end_date=TODAY - dt.timedelta(days=10))  # fmt: skip
    sign_in(db, client, gym_a.owner)
    device = backdate(db, add_reader(client, gym_a)["device"]["id"])
    zk(client, "getrequest")  # both go on the reader

    when = a_little_ago()
    body = "\n".join(
        [
            scan_line(readers.pin_of(sita), when, verify=1),
            scan_line(readers.pin_of(ram), when, verify=15),
            scan_line("9999", when),  # a reader user who isn't a member
        ]
    )
    assert zk(client, "cdata", body, table="ATTLOG", Stamp="1").text == "OK: 3"
    visits = {
        c.member_id: c
        for c in db.scalars(select(CheckIn).where(CheckIn.device_id == device.id))
    }
    assert set(visits) == {sita.id, ram.id}
    assert (visits[sita.id].result, visits[sita.id].method) == (
        ALLOWED,
        METHOD_FINGERPRINT,
    )
    assert visits[sita.id].at == when
    assert visits[sita.id].branch_id == gym_a.branch.id
    # The reader let Ram in; GymBhai records that he shouldn't have been.
    assert (visits[ram.id].result, visits[ram.id].method) == (
        DENIED_EXPIRED,
        METHOD_FACE,
    )

    # Sent again (the reader wasn't sure it arrived): recorded once.
    zk(client, "cdata", body, table="ATTLOG", Stamp="2")
    assert len(db.scalars(select(CheckIn)).all()) == 2


def test_scans_from_before_the_reader_or_a_wrong_clock_are_not_visits(
    client: TestClient, db: Session, gym_a: GymFixture
):
    sita = make_member(db, gym_a)
    sell(db, gym_a, sita, paid=1500_00, start_date=TODAY - dt.timedelta(days=60),
         end_date=TODAY + dt.timedelta(days=30))  # fmt: skip
    sign_in(db, client, gym_a.owner)
    add_reader(client, gym_a)
    zk(client, "getrequest")
    pin = readers.pin_of(sita)
    old = utcnow() - dt.timedelta(days=7)
    ahead = utcnow() + dt.timedelta(hours=3)
    body = "\n".join([scan_line(pin, old), scan_line(pin, ahead), "nonsense"])
    zk(client, "cdata", body, table="ATTLOG")
    assert db.scalars(select(CheckIn)).all() == []


def test_fingerprint_templates_never_stay_here(
    client: TestClient, db: Session, gym_a: GymFixture
):
    sign_in(db, client, gym_a.owner)
    add_reader(client, gym_a)
    template = (
        "FP PIN=1\tFID=6\tSize=1184\tValid=1"
        "\tTMP=SpVTUzIxAAAERE8ECAUHCc7QAAAcRWkBAAAAhPwo"
    )
    assert zk(client, "cdata", template, table="OPERLOG").text == "OK: 1"
    assert db.scalars(select(CheckIn)).all() == []


# --- who a reader should hold -------------------------------------------------------


def test_what_a_reader_holds(client: TestClient, db: Session, gym_a: GymFixture):
    owner = context_for(db, gym_a.owner)
    active = make_member(db, gym_a, name="Active", phone="9800000001")
    membership, _ = sell(db, gym_a, active, paid=1500_00)
    frozen = make_member(db, gym_a, name="Frozen", phone="9800000002")
    held, _ = sell(db, gym_a, frozen, paid=1500_00)
    ms.freeze(db, owner, held, TODAY, TODAY + dt.timedelta(days=5), "Away")
    lapsed = make_member(db, gym_a, name="Lapsed", phone="9800000003")
    sell(db, gym_a, lapsed, paid=1500_00, start_date=TODAY - dt.timedelta(days=50),
         end_date=TODAY - dt.timedelta(days=20))  # fmt: skip
    gone = make_member(db, gym_a, name="Gone", phone="9800000004")
    sell(db, gym_a, gone, paid=1500_00, start_date=TODAY - dt.timedelta(days=200),
         end_date=TODAY - dt.timedelta(days=170))  # fmt: skip
    elsewhere = Branch(gym_id=gym_a.gym.id, name="Koteshwor")
    db.add(elsewhere)
    db.commit()
    sign_in(db, client, gym_a.owner)
    device = db.get(Device, add_reader(client, gym_a, kind="hikvision")["device"]["id"])

    wants = readers.wanted(db, device)
    assert wants[active.id].on_reader and wants[active.id].until == membership.end_date
    # On the reader, but not let in today.
    assert (wants[frozen.id].on_reader, wants[frozen.id].until) == (True, None)
    assert (wants[lapsed.id].on_reader, wants[lapsed.id].until) == (True, None)
    # Stopped coming long ago: not put on it at all.
    assert gone.id not in wants

    # A reader at a branch the plan isn't sold at: kept, not let in.
    made = add_reader(client, gym_a, kind="hikvision", branch_id=str(elsewhere.id))
    other = db.get(Device, made["device"]["id"])
    plan = db.get(Plan, membership.plan_id)
    plan.all_branches = False
    db.add(PlanBranch(plan_id=plan.id, branch_id=gym_a.branch.id))
    db.commit()
    assert readers.wanted(db, other)[active.id].until is None
    assert readers.wanted(db, device)[active.id].until == membership.end_date


def test_renewing_freezing_and_erasing_send_changes(
    client: TestClient, db: Session, gym_a: GymFixture
):
    sita = make_member(db, gym_a)
    membership, _ = sell(db, gym_a, sita, paid=1500_00)
    sign_in(db, client, gym_a.owner)
    token = add_reader(client, gym_a, kind="hikvision")["token"]
    bridge = {"X-Device-Token": token}
    client.headers.pop("Authorization")

    def commands() -> list[dict]:
        # As often as the bridge asks: worked out again each time here.
        db.execute(Device.__table__.update().values(synced_at=None))
        db.commit()
        response = client.get("/api/v1/kiosk/reader/commands", headers=bridge)
        assert response.status_code == 200, response.text
        return response.json()["commands"]

    [first] = commands()
    assert (
        first["action"] == "set" and first["until"] == membership.end_date.isoformat()
    )
    ok = {"results": [{"id": first["id"], "ok": True}]}
    assert (
        client.post("/api/v1/kiosk/reader/results", json=ok, headers=bridge).json()[
            "answered"
        ]
        == 1
    )
    assert commands() == []

    # Renewed: the reader's end date moves.
    renewal, _ = sell(db, gym_a, sita, paid=1500_00)
    [moved] = commands()
    assert moved["until"] == renewal.end_date.isoformat()
    client.post(
        "/api/v1/kiosk/reader/results",
        json={"results": [{"id": moved["id"], "ok": True}]},
        headers=bridge,
    )

    # Erased at their request: taken off the reader.
    sign_in(db, client, gym_a.owner)
    assert client.post(f"/api/v1/members/{sita.id}/erase").status_code == 200
    client.headers.pop("Authorization")
    [off] = commands()
    assert off["action"] == "remove"


def test_the_hikvision_bridge_passes_scans_on(
    client: TestClient, db: Session, gym_a: GymFixture
):
    sita = make_member(db, gym_a)
    sell(db, gym_a, sita, paid=1500_00)
    sign_in(db, client, gym_a.owner)
    made = add_reader(client, gym_a, kind="hikvision")
    backdate(db, made["device"]["id"])
    bridge = {"X-Device-Token": made["token"]}
    client.headers.pop("Authorization")
    client.get("/api/v1/kiosk/reader/commands", headers=bridge)

    event = {
        "pin": readers.pin_of(sita),
        "at": a_little_ago().astimezone(NEPAL).isoformat(),
        "how": "face",
    }
    sent = client.post(
        "/api/v1/kiosk/reader/events", json={"events": [event]}, headers=bridge
    )
    assert sent.json()["recorded"] == 1
    again = client.post(
        "/api/v1/kiosk/reader/events", json={"events": [event]}, headers=bridge
    )
    assert again.json()["recorded"] == 0
    visit = db.scalars(select(CheckIn)).one()
    assert (visit.method, visit.result) == (METHOD_FACE, ALLOWED)

    # A reader's token opens its bridge's routes, not the kiosk's.
    assert (
        client.post(
            "/api/v1/kiosk/scan", json={"code": "x" * 20}, headers=bridge
        ).json()["code"]
        == "not_a_kiosk"
    )


def test_a_kiosk_is_not_a_bridge(client: TestClient, db: Session, gym_a: GymFixture):
    sign_in(db, client, gym_a.owner)
    kiosk = client.post(
        "/api/v1/devices", json={"branch_id": str(gym_a.branch.id), "name": "Door"}
    ).json()
    client.headers.pop("Authorization")
    refused = client.get(
        "/api/v1/kiosk/reader/commands", headers={"X-Device-Token": kiosk["token"]}
    )
    assert (refused.status_code, refused.json()["code"]) == (
        409,
        "not_a_bridged_reader",
    )


def test_a_reader_holds_only_its_own_gyms_members(
    client: TestClient, db: Session, gym_a: GymFixture, gym_b: GymFixture
):
    sell(db, gym_a, make_member(db, gym_a), paid=1500_00)
    sell(db, gym_b, make_member(db, gym_b, phone="9819999999"), paid=1500_00)
    sign_in(db, client, gym_b.owner)
    add_reader(client, gym_b)
    lines = zk(client, "getrequest").text.strip().splitlines()
    assert len(lines) == 1 and "Sita Rai" in lines[0]
    device = db.scalars(select(Device).where(Device.serial == SERIAL)).one()
    assert (
        {row.gym_id for row in db.scalars(select(ReaderUser))}
        == {device.gym_id}
        == {gym_b.gym.id}
    )


def test_the_profile_says_their_number_on_the_reader(
    client: TestClient, db: Session, gym_a: GymFixture
):
    sita = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    assert client.get(f"/api/v1/members/{sita.id}").json()["reader_pin"] is None
    add_reader(client, gym_a)
    detail = client.get(f"/api/v1/members/{sita.id}").json()
    # HFC-0001 is 1 on the reader.
    assert (
        detail["reader_pin"]
        == readers.pin_of(sita)
        == sita.member_code.split("-")[1].lstrip("0")
    )
