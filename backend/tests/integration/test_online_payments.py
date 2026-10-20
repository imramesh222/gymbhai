"""Members' app payments confirmed by the wallet (PLAN.md §20.2), through the
console wallet that stands in for eSewa, Khalti and Fonepay."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.activity import ActivityLog
from app.models.job import Job
from app.models.member_app import OnlinePayment, PaymentRequest
from app.models.membership import Membership
from app.models.payment import GymPaymentMethod, Payment
from app.services import member_auth
from app.services import online_payments as service
from tests.conftest import GymFixture, make_member, priced_plan, sell, sign_in


@pytest.fixture
def setup(client: TestClient, db: Session, gym_a: GymFixture):
    member = make_member(db, gym_a)
    current, _ = sell(db, gym_a, member, paid=1500_00)
    plan = priced_plan(db, gym_a.gym)
    esewa = GymPaymentMethod(gym_id=gym_a.gym.id, kind="esewa", label="eSewa")
    db.add(esewa)
    db.commit()
    issued = member_auth.start_session(db, member, None)
    db.commit()
    app = TestClient(client.app)
    app.headers["Authorization"] = f"Bearer {issued.access_token}"
    sign_in(db, client, gym_a.owner)
    keys = client.put(
        f"/api/v1/payment-methods/{esewa.id}/gateway",
        json={"merchant": "NP-ES-GYM", "secret_key": "8gBm/:&EnhH.1/q"},
    )
    assert keys.status_code == 200, keys.text
    return member, current, plan, esewa, app


def start(app: TestClient, plan, esewa, **extra):
    return app.post(
        "/api/v1/m/online-payments",
        json={"plan_id": str(plan.id), "payment_method_id": str(esewa.id), **extra},
    )


def token_of(started: dict) -> str:
    return started["pay_url"].rsplit("/pay/", 1)[1]


def test_keys_are_kept_but_never_shown(client: TestClient, db: Session, setup) -> None:
    _, _, _, esewa, app = setup
    staff_view = client.get("/api/v1/payment-methods").json()[0]
    assert staff_view["online"] is True
    assert staff_view["gateway"] == {
        "merchant": "NP-ES-GYM",
        "hint": ".1/q",
        "test": False,
        "ok_at": None,
        "error": None,
    }
    db.refresh(esewa)
    assert "8gBm" not in (esewa.gateway_secret or "")
    # Members see only that the wallet confirms payments.
    member_view = app.get("/api/v1/m/renew").json()["payment_methods"][0]
    assert member_view["online"] is True and member_view["gateway"] is None
    # The log says it happened, not what the keys are.
    entry = db.scalars(
        select(ActivityLog).where(ActivityLog.action == "payment_method.gateway_set")
    ).one()
    assert "8gBm" not in str(entry.changes)

    removed = client.delete(f"/api/v1/payment-methods/{esewa.id}/gateway").json()
    assert removed["online"] is False and removed["gateway"] is None


def test_each_wallet_needs_its_own_keys(client: TestClient, db: Session, setup) -> None:
    _, _, _, _, _ = setup
    gym_id = db.scalars(select(GymPaymentMethod.gym_id)).first()
    fonepay = GymPaymentMethod(gym_id=gym_id, kind="fonepay", label="Fonepay")
    bank = GymPaymentMethod(gym_id=gym_id, kind="bank", label="NIC Asia")
    db.add_all([fonepay, bank])
    db.commit()
    short = client.put(
        f"/api/v1/payment-methods/{fonepay.id}/gateway",
        json={"merchant": "FP1", "secret_key": "abcd1234"},
    )
    assert short.status_code == 422
    assert short.json()["missing"] == ["username", "password"]
    refused = client.put(
        f"/api/v1/payment-methods/{bank.id}/gateway", json={"secret_key": "abcd1234"}
    )
    assert refused.json()["code"] == "gateway_kind"


def test_paid_through_the_wallet_renews_by_itself(
    client: TestClient, db: Session, setup
) -> None:
    member, current, plan, esewa, app = setup
    started = start(app, plan, esewa)
    assert started.status_code == 201, started.text
    body = started.json()
    assert (body["status"], body["amount"], body["provider"]) == (
        "started",
        1500_00,
        "esewa",
    )
    # The worker will ask, for the member who closes the page.
    assert db.scalars(select(Job).where(Job.kind == service.JOB_CHECK)).one()

    page = client.get(f"/api/v1/pay/{token_of(body)}").json()
    assert page["checkout"]["kind"] == "console"
    assert page["gym_slug"] == "fitness-zone"
    # Not paid yet: asking changes nothing.
    assert client.post(f"/api/v1/pay/{token_of(body)}/check").json()["status"] == (
        "started"
    )

    paid = client.post(f"/api/v1/pay/{token_of(body)}/pretend", json={"paid": True})
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "paid" and paid.json()["approved"] is True
    assert paid.json()["checkout"] is None

    request = db.scalars(select(PaymentRequest)).one()
    assert (request.status, request.confirmed_by, request.reviewed_by) == (
        "approved",
        "esewa",
        None,
    )
    renewal = db.get(Membership, request.membership_id)
    assert renewal is not None
    assert renewal.start_date == current.end_date + dt.timedelta(days=1)
    payment = db.get(Payment, request.payment_id)
    assert payment is not None
    assert (payment.amount, payment.method, payment.received_by) == (
        1500_00,
        "esewa",
        None,
    )
    assert payment.transaction_ref and payment.transaction_ref.startswith("TEST")
    assert payment.note == "From the member app, confirmed by eSewa"
    # Done by GymBhai for the gym, not by any of its staff.
    approved = db.scalars(
        select(ActivityLog).where(ActivityLog.action == "payment_request.approved")
    ).one()
    assert (approved.actor_type, approved.actor_id) == ("system", None)
    # Nothing waits for the desk.
    assert client.get("/api/v1/payment-requests/count").json() == {"pending": 0}
    # Asked again (the member's page and the worker), it's sold once.
    client.post(f"/api/v1/pay/{token_of(body)}/check")
    app.post(f"/api/v1/m/online-payments/{body['id']}/check")
    service.check(db, body["id"])
    db.commit()
    assert (
        len(
            db.scalars(
                select(Membership).where(Membership.member_id == member.id)
            ).all()
        )
        == 2
    )


def test_cancelled_on_the_wallet_sells_nothing(
    client: TestClient, db: Session, setup
) -> None:
    _, _, plan, esewa, app = setup
    body = start(app, plan, esewa).json()
    page = client.post(f"/api/v1/pay/{token_of(body)}/pretend", json={"paid": False})
    assert page.json()["status"] == "failed"
    assert db.scalars(select(PaymentRequest)).all() == []
    # They can try again.
    assert start(app, plan, esewa).status_code == 201


def test_back_to_the_app_that_started_it(
    client: TestClient, db: Session, setup
) -> None:
    """A gym's own app, or Expo Go while developing, isn't gymbhai:// (§20.3)."""
    _, _, plan, esewa, app = setup
    own_app = "gb-fitness-zone://renew"
    body = start(app, plan, esewa, from_app=True, return_to=own_app).json()
    page = client.get(f"/api/v1/pay/{token_of(body)}").json()
    assert (page["from_app"], page["return_to"]) == (True, own_app)
    # Only the apps' own links: never somewhere else on the web.
    for elsewhere in ("https://example.com", "javascript:alert(1)"):
        refused = start(app, plan, esewa, from_app=True, return_to=elsewhere)
        assert refused.status_code == 422
    # The web app's checkout goes back to the gym's page, not an app.
    web = start(app, plan, esewa, return_to=own_app)
    assert client.get(f"/api/v1/pay/{token_of(web.json())}").json()["return_to"] is None


def test_the_amount_is_the_servers(client: TestClient, db: Session, setup) -> None:
    _, _, plan, esewa, app = setup
    sent = start(app, plan, esewa, amount=1_00)
    assert sent.status_code == 422  # no such field: Strict
    plan.admission_fee = 500_00
    db.commit()
    # A renewal pays no admission fee: only a first membership does.
    assert start(app, plan, esewa).json()["amount"] == 1500_00


def test_a_request_waiting_blocks_starting_one(
    client: TestClient, db: Session, setup
) -> None:
    _, _, plan, esewa, app = setup
    manual = app.post(
        "/api/v1/m/payment-requests",
        json={"plan_id": str(plan.id), "amount": 1500_00, "transaction_ref": "ES-9"},
    )
    assert manual.status_code == 201
    blocked = start(app, plan, esewa)
    assert blocked.status_code == 409 and blocked.json()["code"] == "request_pending"


def test_a_changed_price_waits_for_the_desk(
    client: TestClient, db: Session, setup
) -> None:
    _, _, plan, esewa, app = setup
    body = start(app, plan, esewa).json()
    plan.price = 1800_00
    db.commit()
    client.post(f"/api/v1/pay/{token_of(body)}/pretend", json={"paid": True})
    request = db.scalars(select(PaymentRequest)).one()
    assert (request.status, request.confirmed_by, request.amount) == (
        "pending",
        "esewa",
        1500_00,
    )
    [listed] = client.get("/api/v1/payment-requests").json()
    assert listed["confirmed_by"] == "esewa"
    assert db.scalars(select(Payment).where(Payment.method == "esewa")).all() == []


def test_paid_after_starting_another_waits_for_the_desk(
    client: TestClient, db: Session, setup
) -> None:
    _, _, plan, esewa, app = setup
    first = start(app, plan, esewa).json()
    second = start(app, plan, esewa).json()
    client.post(f"/api/v1/pay/{token_of(second)}/pretend", json={"paid": True})
    assert db.scalars(select(PaymentRequest)).one().status == "approved"
    # The first was paid too: two renewals for one member is the desk's call.
    client.post(f"/api/v1/pay/{token_of(first)}/pretend", json={"paid": True})
    statuses = sorted(r.status for r in db.scalars(select(PaymentRequest)))
    assert statuses == ["approved", "pending"]


def test_the_wallets_test_system_sells_nothing(
    client: TestClient, db: Session, setup, monkeypatch
) -> None:
    _, _, plan, esewa, app = setup
    client.put(
        f"/api/v1/payment-methods/{esewa.id}/gateway",
        json={"merchant": "EPAYTEST", "secret_key": "8gBm/:&EnhH.1/q", "test": True},
    )
    # As on a server with GATEWAY_PROVIDER=live, the wallet answering "paid".
    monkeypatch.setattr(settings, "gateway_provider", "live")
    from app.services.gateways import providers

    class Paid:
        def start(self, keys, order):
            return providers.Checkout(kind="form", url="https://x", fields={})

        def check(self, keys, order, details):
            return providers.Answer(providers.PAID, transaction_ref="0001TS9")

    monkeypatch.setattr(service, "_gateway", lambda kind: Paid())
    body = start(app, plan, esewa).json()
    assert body["test"] is True
    page = client.post(f"/api/v1/pay/{token_of(body)}/check").json()
    assert page["status"] == "paid" and page["approved"] is False
    assert db.scalars(select(PaymentRequest)).all() == []
    assert db.scalars(select(Payment).where(Payment.method == "esewa")).all() == []


def test_the_worker_asks_until_it_is_settled(
    client: TestClient, db: Session, setup, monkeypatch
) -> None:
    _, _, plan, esewa, app = setup
    body = start(app, plan, esewa).json()
    row = db.get(OnlinePayment, body["id"])
    assert row is not None
    service.handle_check(db, {"id": body["id"]})
    db.commit()
    assert db.scalar(
        select(Job).where(Job.kind == service.JOB_CHECK).order_by(Job.run_at.desc())
    )
    assert len(db.scalars(select(Job).where(Job.kind == service.JOB_CHECK)).all()) == 2

    # Past its time, the wallet still saying "not paid": expired, no more asks.
    row.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
    db.commit()
    service.handle_check(db, {"id": body["id"]})
    db.commit()
    db.refresh(row)
    assert row.status == "expired"
    assert len(db.scalars(select(Job).where(Job.kind == service.JOB_CHECK)).all()) == 2


def test_an_unreachable_wallet_never_expires_a_payment_early(
    client: TestClient, db: Session, setup, monkeypatch
) -> None:
    _, _, plan, esewa, app = setup
    body = start(app, plan, esewa).json()
    row = db.get(OnlinePayment, body["id"])
    assert row is not None
    row.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
    db.commit()
    from app.services.gateways import providers

    class Down:
        def check(self, keys, order, details):
            raise providers.GatewayError("timed out")

    monkeypatch.setattr(service, "_gateway", lambda kind: Down())
    service.check(db, row.id)
    db.commit()
    db.refresh(row)
    assert (row.status, row.error) == ("started", "timed out")


def test_a_wallet_refusing_the_keys_shows_in_settings(
    client: TestClient, db: Session, setup, monkeypatch
) -> None:
    _, _, plan, esewa, app = setup
    from app.services.gateways import providers

    class Refusing:
        def start(self, keys, order):
            raise providers.KeysRefused("Invalid merchant")

    monkeypatch.setattr(service, "_gateway", lambda kind: Refusing())
    refused = start(app, plan, esewa)
    assert refused.status_code == 502 and refused.json()["code"] == "gateway_keys"
    gateway = client.get("/api/v1/payment-methods").json()[0]["gateway"]
    assert gateway["error"] == "Invalid merchant"


def test_links_and_payments_are_their_own(
    client: TestClient, db: Session, setup, gym_b: GymFixture
) -> None:
    _, _, plan, esewa, app = setup
    body = start(app, plan, esewa).json()
    token = token_of(body)
    assert client.get(f"/api/v1/pay/{token[:-2]}xx").status_code == 404
    assert client.get("/api/v1/pay/not-a-token").status_code == 404
    # Another member, even of the same gym, doesn't find it.
    other = make_member(db, gym_b, phone="9800000001")
    issued = member_auth.start_session(db, other, None)
    db.commit()
    stranger = TestClient(client.app)
    stranger.headers["Authorization"] = f"Bearer {issued.access_token}"
    assert stranger.get(f"/api/v1/m/online-payments/{body['id']}").status_code == 404
    # Nor another gym's account.
    assert (
        stranger.post(
            "/api/v1/m/online-payments",
            json={"plan_id": str(plan.id), "payment_method_id": str(esewa.id)},
        ).status_code
        == 422
    )
    sign_in(db, client, gym_b.owner)
    assert (
        client.put(
            f"/api/v1/payment-methods/{esewa.id}/gateway",
            json={"merchant": "X", "secret_key": "abcd1234"},
        ).status_code
        == 404
    )


def test_the_pretend_wallet_is_for_development_only(
    client: TestClient, db: Session, setup, monkeypatch
) -> None:
    _, _, plan, esewa, app = setup
    body = start(app, plan, esewa).json()
    monkeypatch.setattr(settings, "gateway_provider", "live")
    refused = client.post(f"/api/v1/pay/{token_of(body)}/pretend", json={"paid": True})
    assert refused.status_code == 404


def test_off_on_a_server_without_live_wallets(
    client: TestClient, db: Session, setup, monkeypatch
) -> None:
    _, _, plan, esewa, app = setup
    monkeypatch.setattr(settings, "environment", "production")
    assert app.get("/api/v1/m/renew").json()["payment_methods"][0]["online"] is False
    assert start(app, plan, esewa).status_code == 422
