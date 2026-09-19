import datetime as dt
import io

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.core.calendar import to_bs
from app.core.time import today_in_nepal
from app.services import checkins
from tests.conftest import GymFixture, make_member, sell, sign_in

TODAY = today_in_nepal()


def check_in(db: Session, fixture: GymFixture, member) -> None:
    checkins.check_in(
        db, gym=fixture.gym, member=member, branch_id=fixture.branch.id, method="manual"
    )
    db.commit()


def test_today(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    paid = make_member(db, gym_a, name="Paid", phone="9800000001")
    sell(db, gym_a, paid, paid=1500_00)
    owing = make_member(db, gym_a, name="Owing", phone="9800000002")
    sell(db, gym_a, owing, paid=500_00, start_date=TODAY - dt.timedelta(days=25),
         end_date=TODAY + dt.timedelta(days=3))  # fmt: skip
    lapsed = make_member(db, gym_a, name="Lapsed", phone="9800000003")
    for m in (paid, lapsed):
        check_in(db, gym_a, m)
    sign_in(db, client, gym_a.owner)

    today = client.get("/api/v1/dashboard/today").json()
    assert today["check_ins"] == 1
    assert [p["name"] for p in today["inside_now"]] == ["Paid"]
    assert [p["name"] for p in today["turned_away"]] == ["Lapsed"]
    assert today["expiring_this_week"] == 1
    assert today["members_with_dues"] == 1 and today["dues_total"] == 1000_00
    assert today["collected"] == 2000_00
    assert today["active_members"] == 2


def test_money_is_hidden_without_the_permission(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
) -> None:
    sign_in(db, client, make_staff(gym_a.gym, permissions=["members.view"]))
    today = client.get("/api/v1/dashboard/today").json()
    assert today["collected"] is None and today["pending_requests"] is None


def test_monthly_report_in_bs_months(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    # gym_a shows dates in AD and BS, so months are BS months.
    first = make_member(db, gym_a, name="First", phone="9800000011")
    sell(db, gym_a, first, paid=1500_00)
    renewer = make_member(db, gym_a, name="Renewer", phone="9800000012")
    old, _ = sell(db, gym_a, renewer, paid=1500_00)
    sell(
        db, gym_a, renewer, paid=1500_00, start_date=old.end_date + dt.timedelta(days=1)
    )
    sign_in(db, client, gym_a.owner)

    year, month, _ = to_bs(TODAY)
    report = client.get("/api/v1/reports/monthly").json()
    assert report["month"] == f"{year}-{month:02d}" and report["calendar"] == "bs"
    assert report["income"] == 4500_00
    assert report["income_by_method"] == {"cash": 4500_00}
    assert report["new_members"] == 2
    assert report["new_memberships"] == 2 and report["renewals"] == 1
    assert report["by_plan"] == {"1 month": 3}
    assert report["active_members"] == 2

    earlier = client.get(
        "/api/v1/reports/monthly", params={"month": f"{year - 1}-01"}
    ).json()
    assert earlier["income"] == 0
    assert (
        client.get("/api/v1/reports/monthly", params={"month": "2083-13"}).status_code
        == 422
    )


def test_ad_gyms_get_ad_months(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    client.patch("/api/v1/gym", json={"settings": {"date_display": "ad"}})
    report = client.get("/api/v1/reports/monthly").json()
    assert report["month"] == f"{TODAY:%Y-%m}" and report["calendar"] == "ad"
    assert report["first_day"] == f"{TODAY:%Y-%m}-01"


def workbook(response) -> list[list]:
    sheet = load_workbook(io.BytesIO(response.content)).active
    return [list(row) for row in sheet.iter_rows(values_only=True)]


def test_exports(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    member = make_member(db, gym_a)
    sell(db, gym_a, member, paid=1000_00)
    check_in(db, gym_a, member)
    sign_in(db, client, gym_a.owner)

    members = client.get("/api/v1/export/members.xlsx")
    assert members.headers["content-type"].startswith("application/vnd.openxmlformats")
    rows = workbook(members)
    header = rows[0]
    sita = dict(zip(header, rows[1], strict=True))
    assert sita["Name"] == "Sita Rai" and sita["Owes (Rs)"] == 500
    assert "Valid until (BS)" in header

    payments = workbook(client.get("/api/v1/export/payments.xlsx"))
    assert payments[1][5] == 1000  # rupees, not paisa
    assert len(workbook(client.get("/api/v1/export/memberships.xlsx"))) == 2
    assert len(workbook(client.get("/api/v1/export/check-ins.xlsx"))) == 2
    assert client.get("/api/v1/export/secrets.xlsx").status_code == 422


def test_payments_export_needs_money_permission(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
) -> None:
    sign_in(db, client, make_staff(gym_a.gym, permissions=["members.view"]))
    assert client.get("/api/v1/export/members.xlsx").status_code == 200
    assert client.get("/api/v1/export/payments.xlsx").status_code == 403
