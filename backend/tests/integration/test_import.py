from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.calendar import from_bs
from app.models.member import Member
from app.models.membership import Membership
from app.models.messaging import SmsMessage
from tests.conftest import GymFixture, make_member, sign_in

REGISTER = """Member Name,Mobile No,Package,Expiry Date,Remarks
Hari Thapa,+977 984-1111111,3 months,2083-09-15,morning
Gita Rai,9812222222,1 month,2026-12-01,
No Phone,,1 month,2026-12-01,
Bad Date,9813333333,1 month,31/31/2026,
Sita Rai,9812345678,1 month,2026-12-01,already here
"""


def upload(client: TestClient, text: str = REGISTER, name: str = "register.csv"):
    return client.post(
        "/api/v1/members/import", files={"file": (name, text.encode(), "text/csv")}
    )


def test_import_a_register(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    make_member(db, gym_a)  # Sita Rai, 9812345678
    sign_in(db, client, gym_a.owner)

    preview = upload(client).json()
    assert preview["total_rows"] == 5
    mapping = preview["mapping"]
    assert mapping["name"] == 0 and mapping["phone"] == 1
    assert (
        mapping["plan_name"] == 2 and mapping["end_date"] == 3 and mapping["notes"] == 4
    )
    assert preview["ready"] == 3
    assert [p[0] for p in preview["problems"]] == [3, 4]
    # Nothing saved yet.
    assert db.scalar(select(Member).where(Member.name == "Hari Thapa")) is None

    done = client.post(f"/api/v1/members/import/{preview['id']}/commit", json={}).json()
    assert done["status"] == "committed"
    assert done["result"]["created"] == 2 and done["result"]["skipped"] == 1

    hari = db.scalars(select(Member).where(Member.name == "Hari Thapa")).one()
    assert hari.phone == "9841111111" and hari.notes == "morning"
    membership = db.scalars(
        select(Membership).where(Membership.member_id == hari.id)
    ).one()
    # A BS date in the register is read as BS.
    assert membership.end_date == from_bs(2083, 9, 15)
    assert membership.plan_name == "3 months" and membership.price == 0
    assert membership.source == "import"
    # No SMS to people who haven't heard of the app yet.
    assert (
        db.scalars(select(SmsMessage).where(SmsMessage.kind == "welcome")).first()
        is None
    )

    again = client.post(f"/api/v1/members/import/{preview['id']}/commit", json={})
    assert again.json()["code"] == "import_done"


def test_remap_columns_before_commit(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    text = "A,B\nRam Bahadur,9800000099\n"
    preview = upload(client, text).json()
    assert preview["ready"] == 0
    mapping = {"name": 0, "phone": 1}
    checked = client.post(
        f"/api/v1/members/import/{preview['id']}/preview", json={"mapping": mapping}
    ).json()
    assert checked["ready"] == 1


def test_only_spreadsheets(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    sign_in(db, client, gym_a.owner)
    assert upload(client, "x", "register.pdf").status_code == 415
