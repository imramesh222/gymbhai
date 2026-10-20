"""The shop at the desk (PLAN.md §20.1): products and their stock, a sale paid
in full as an ordinary payment, walk-ins, voids that put the stock back, and
the money in Payments, Reports and the exports."""

import io
from urllib.parse import urlsplit

import openpyxl
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.activity import ActivityLog
from app.models.gym import Branch
from app.models.payment import Payment
from app.models.shop import ProductSale, StockMove
from tests.conftest import GymFixture, make_member, sign_in


def product(client: TestClient, name="Whey 1 kg", price=4500_00, **extra) -> dict:
    response = client.post(
        "/api/v1/products",
        json={"name": name, "category": "supplement", "price": price, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


def sale(client: TestClient, *lines: tuple[dict, int], key: str | None = None, **body):
    payload = {
        "lines": [{"product_id": p["id"], "quantity": n} for p, n in lines],
        **body,
    }
    headers = {"Idempotency-Key": key} if key else {}
    return client.post("/api/v1/sales", json=payload, headers=headers)


def test_products_and_their_stock(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    whey = product(client, stock=10, low_stock=3, code="8901234567890")
    assert (whey["stock"], whey["low_stock"]) == (10, 3)
    water = product(client, "Water", 50_00, category="drink")
    assert water["stock"] is None  # not counted
    taken = client.post(
        "/api/v1/products", json={"name": "Copy", "price": 1, "code": "8901234567890"}
    )
    assert taken.json()["code"] == "code_taken"

    restocked = client.post(
        f"/api/v1/products/{whey['id']}/stock",
        json={"kind": "restock", "quantity": 12, "note": "From the supplier"},
    ).json()
    assert restocked["stock"] == 22
    counted = client.post(
        f"/api/v1/products/{whey['id']}/stock", json={"kind": "count", "quantity": 20}
    ).json()
    assert counted["stock"] == 20
    history = client.get(f"/api/v1/products/{whey['id']}/stock").json()
    assert sorted(m["change"] for m in history) == [-2, 10, 12]
    # Water starts being counted when it's counted.
    assert client.post(
        f"/api/v1/products/{water['id']}/stock", json={"kind": "count", "quantity": 48}
    ).json()["stock"] == 48  # fmt: skip
    off = client.patch(
        f"/api/v1/products/{water['id']}", json={"track_stock": False, "price": 60_00}
    ).json()
    assert (off["stock"], off["price"]) == (None, 60_00)
    hidden = client.patch(f"/api/v1/products/{water['id']}", json={"is_active": False})
    assert hidden.status_code == 200
    names = [p["name"] for p in client.get("/api/v1/products").json()]
    assert names == ["Whey 1 kg"]
    everything = client.get("/api/v1/products?include_hidden=true").json()
    assert len(everything) == 2
    actions = set(
        db.scalars(select(ActivityLog.action).where(ActivityLog.entity == "product"))
    )
    assert {"product.created", "product.restock", "product.count"} <= actions


def test_a_sale_to_a_member_and_one_to_a_walk_in(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    whey = product(client, stock=5)
    water = product(client, "Water", 50_00, category="drink")
    member = make_member(db, gym_a, phone="9814000001")

    sold = sale(
        client,
        (whey, 2),
        (water, 1),
        (whey, 1),  # the same product twice counts once
        member_id=str(member.id),
        discount=500_00,
        payment={"method": "esewa", "transaction_ref": "ESW123"},
        key="sale-0001-0001-0001",
    )
    assert sold.status_code == 201, sold.text
    body = sold.json()
    assert body["total"] == 3 * 4500_00 + 50_00 - 500_00
    assert body["member_name"] == "Sita Rai"
    assert {(line["name"], line["quantity"]) for line in body["lines"]} == {
        ("Whey 1 kg", 3),
        ("Water", 1),
    }
    # A double tap sells once.
    again = sale(
        client,
        (whey, 2),
        (water, 1),
        (whey, 1),
        member_id=str(member.id),
        discount=500_00,
        payment={"method": "esewa", "transaction_ref": "ESW123"},
        key="sale-0001-0001-0001",
    )
    assert again.json()["id"] == body["id"]
    stock = client.get("/api/v1/products").json()
    assert {p["name"]: p["stock"] for p in stock} == {"Whey 1 kg": 2, "Water": None}

    payment = db.get(Payment, body["payment_id"])
    assert (payment.amount, payment.method, payment.member_id) == (
        body["total"],
        "esewa",
        member.id,
    )
    walk_in = sale(client, (water, 2))
    assert walk_in.status_code == 201
    assert walk_in.json()["member_name"] is None
    assert db.get(Payment, walk_in.json()["payment_id"]).member_id is None

    # Too few left, a used transaction ID, nothing to pay: refused.
    assert sale(client, (whey, 3)).json()["code"] == "out_of_stock"
    assert (
        sale(
            client, (water, 1), payment={"method": "esewa", "transaction_ref": "ESW123"}
        ).json()["code"]
        == "transaction_ref_used"
    )
    assert sale(client, (water, 1), discount=50_00).json()["code"] == "nothing_to_pay"

    # In Payments, with the walk-in's having nobody's name.
    listed = client.get("/api/v1/payments").json()
    assert listed["sum_amount"] == body["total"] + 100_00
    assert {i["member_name"] for i in listed["items"]} == {"Sita Rai", None}
    # The receipt names what was bought.
    receipt = client.get(f"/api/v1/payments/{body['payment_id']}/receipt").json()
    # By name, whatever order they went in the basket.
    assert [(i["name"], i["quantity"]) for i in receipt["items"]] == [
        ("Water", 1),
        ("Whey 1 kg", 3),
    ]
    assert receipt["discount"] == 500_00
    walk_receipt = client.get(
        f"/api/v1/payments/{walk_in.json()['payment_id']}/receipt"
    ).json()
    assert walk_receipt["member_name"] is None
    link = client.post(
        f"/api/v1/payments/{walk_in.json()['payment_id']}/receipt-link"
    ).json()
    url = urlsplit(link["url"])
    pdf = client.get(f"{url.path}?{url.query}")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_voiding_puts_the_stock_back(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    whey = product(client, stock=5)
    first = sale(client, (whey, 2)).json()
    second = sale(client, (whey, 1)).json()

    voided = client.post(
        f"/api/v1/sales/{first['id']}/void", json={"reason": "Wrong flavour"}
    ).json()
    assert voided["voided_at"] and voided["void_reason"] == "Wrong flavour"
    assert db.get(Payment, first["payment_id"]).voided_at is not None
    # Voiding the payment voids the sale, and its stock comes back too.
    response = client.post(
        f"/api/v1/payments/{second['payment_id']}/void", json={"reason": "Mistake"}
    )
    assert response.status_code == 200
    assert db.get(ProductSale, second["id"]).voided_at is not None
    assert client.get("/api/v1/products").json()[0]["stock"] == 5
    reasons = [m.reason for m in db.scalars(select(StockMove))]
    assert reasons.count("void") == 2
    twice = client.post(f"/api/v1/sales/{first['id']}/void", json={"reason": "Again"})
    assert twice.json()["code"] == "sale_voided"
    # A sale's amount is what was sold: it isn't edited, it's sold again.
    third = sale(client, (whey, 1)).json()
    edit = client.patch(
        f"/api/v1/payments/{third['payment_id']}", json={"amount": 100_00}
    )
    assert edit.json()["code"] == "sale_amount"
    assert (
        client.patch(
            f"/api/v1/payments/{third['payment_id']}", json={"method": "khalti"}
        ).status_code
        == 200
    )


def test_permissions_and_branches(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
) -> None:
    sign_in(db, client, gym_a.owner)
    whey = product(client, stock=5)
    other = Branch(gym_id=gym_a.gym.id, name="Koteshwor")
    db.add(other)
    db.commit()
    elsewhere = sale(client, (whey, 1), branch_id=str(other.id)).json()

    desk = make_staff(gym_a.gym, permissions=["shop.sell"], branches=[gym_a.branch])
    sign_in(db, client, desk)
    assert [p["name"] for p in client.get("/api/v1/products").json()] == ["Whey 1 kg"]
    assert (
        client.post("/api/v1/products", json={"name": "X", "price": 1}).status_code
        == 403
    )
    assert sale(client, (whey, 1)).status_code == 201
    assert sale(client, (whey, 1), branch_id=str(other.id)).status_code == 403
    assert client.get("/api/v1/sales").status_code == 403  # the month is money
    assert (
        client.post(
            f"/api/v1/sales/{elsewhere['id']}/void", json={"reason": "not mine"}
        ).status_code
        == 403
    )
    money = make_staff(
        gym_a.gym,
        permissions=["reports.money", "payments.void"],
        branches=[gym_a.branch],
    )
    sign_in(db, client, money)
    month = client.get("/api/v1/sales").json()
    # Their branch's sale only, not Koteshwor's.
    assert month["count"] == 1 and len(month["items"]) == 1
    assert (
        client.post(
            f"/api/v1/sales/{elsewhere['id']}/void", json={"reason": "not mine"}
        ).status_code
        == 404
    )
    nobody = make_staff(gym_a.gym, permissions=["members.view"])
    sign_in(db, client, nobody)
    assert client.get("/api/v1/products").status_code == 403


def test_reports_today_and_the_exports(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    assert client.get("/api/v1/reports/monthly").json()["shop"] is None
    whey = product(client, stock=5)
    water = product(client, "Water", 50_00, category="drink")
    sale(client, (whey, 1), (water, 2))
    voided = sale(client, (water, 1)).json()
    client.post(f"/api/v1/sales/{voided['id']}/void", json={"reason": "Mistake"})

    report = client.get("/api/v1/reports/monthly").json()
    assert report["shop"]["income"] == 4600_00
    assert report["shop"]["sales"] == 1
    assert report["shop"]["by_category"] == {"supplement": 4500_00, "drink": 100_00}
    assert report["shop"]["top"][0] == {
        "name": "Whey 1 kg",
        "quantity": 1,
        "amount": 4500_00,
    }
    # Already within the month's income, and today's money.
    assert report["income"] == 4600_00
    assert client.get("/api/v1/dashboard/today").json()["collected"] == 4600_00

    sales_book = client.get("/api/v1/export/sales.xlsx")
    assert sales_book.status_code == 200
    rows = list(openpyxl.load_workbook(io.BytesIO(sales_book.content)).active.values)
    assert rows[0][4] == "Product"
    assert {(r[3], r[4], r[6]) for r in rows[1:]} == {
        ("Walk-in", "Whey 1 kg", 1),
        ("Walk-in", "Water", 2),
        ("Walk-in", "Water", 1),
    }
    payments = client.get("/api/v1/export/payments.xlsx")
    rows = list(openpyxl.load_workbook(io.BytesIO(payments.content)).active.values)
    assert {(r[3], r[5]) for r in rows[1:]} == {("Walk-in", "Shop")}
