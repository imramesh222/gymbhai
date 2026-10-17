"""Receipts as PDF, shared by link (PLAN.md §16.3, 8.4)."""

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.services import member_auth
from app.services.receipts import rupees
from tests.conftest import GymFixture, make_member, sell, sign_in

CODE = "123456"


def text_of(pdf: bytes) -> str:
    import io

    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


def path_of(url: str) -> str:
    parts = urlparse(url)
    return f"{parts.path}?{parts.query}"


def test_staff_share_a_receipt(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a, name="Sita Rai")
    _, payment = sell(db, gym_a, member, paid=1000_00)
    sign_in(db, client, gym_a.owner)

    link = client.post(f"/api/v1/payments/{payment.id}/receipt-link").json()
    assert link["filename"] == f"receipt-{payment.receipt_no}.pdf"
    assert link["text"] == (
        f"{gym_a.gym.name}: Payment receipt #{payment.receipt_no}, Rs 1,000"
    )
    # Anyone with the link: no sign-in.
    client.headers.pop("Authorization", None)
    client.cookies.clear()
    response = client.get(path_of(link["url"]))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    text = text_of(response.content)
    for expected in (gym_a.gym.name, "Sita Rai", "Rs 1,000", "Still owed: Rs 500",
                     "not a VAT invoice"):  # fmt: skip
        assert expected in text, expected


def test_a_tampered_or_old_link_opens_nothing(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a)
    _, payment = sell(db, gym_a, member, paid=1500_00)
    _, other = sell(db, gym_a, member, paid=1500_00)
    sign_in(db, client, gym_a.owner)
    url = client.post(f"/api/v1/payments/{payment.id}/receipt-link").json()["url"]
    query = parse_qs(urlparse(url).query)
    exp, sig = query["exp"][0], query["sig"][0]

    # Another payment with this payment's signature.
    assert (
        client.get(f"/api/v1/receipts/{other.id}.pdf?exp={exp}&sig={sig}").status_code
        == 404
    )
    # A later expiry with the same signature.
    later = int(exp) + 86400
    assert (
        client.get(
            f"/api/v1/receipts/{payment.id}.pdf?exp={later}&sig={sig}"
        ).status_code
        == 404
    )
    # Expired.
    old = 1_600_000_000
    assert (
        client.get(f"/api/v1/receipts/{payment.id}.pdf?exp={old}&sig={sig}").status_code
        == 404
    )


def test_another_gyms_payment_is_404(
    client: TestClient, db: Session, gym_a: GymFixture, gym_b: GymFixture
) -> None:
    member = make_member(db, gym_b)
    _, payment = sell(db, gym_b, member, paid=1500_00)
    sign_in(db, client, gym_a.owner)
    assert client.post(f"/api/v1/payments/{payment.id}/receipt-link").status_code == 404


def test_members_download_their_own(
    client: TestClient, db: Session, gym_a: GymFixture, monkeypatch
) -> None:
    monkeypatch.setattr(member_auth.secrets, "randbelow", lambda n: int(CODE))
    mine = make_member(db, gym_a, phone="9800000501")
    _, payment = sell(db, gym_a, mine, paid=1500_00)
    someone = make_member(db, gym_a, phone="9800000502", name="Hari")
    _, theirs = sell(db, gym_a, someone, paid=1500_00)
    slug = gym_a.gym.slug
    client.post(f"/api/v1/m/{slug}/otp/request", json={"phone": mine.phone})
    token = client.post(
        f"/api/v1/m/{slug}/otp/verify", json={"phone": mine.phone, "code": CODE}
    ).json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"

    link = client.post(f"/api/v1/m/me/payments/{payment.id}/receipt-link")
    assert link.status_code == 200
    assert client.get(path_of(link.json()["url"])).status_code == 200
    assert (
        client.post(f"/api/v1/m/me/payments/{theirs.id}/receipt-link").status_code
        == 404
    )


def test_nepali_names_and_grouping(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a, name="सीता राई")
    _, payment = sell(db, gym_a, member, paid=1500_00)
    sign_in(db, client, gym_a.owner)
    url = client.post(f"/api/v1/payments/{payment.id}/receipt-link").json()["url"]
    response = client.get(path_of(url))
    assert response.status_code == 200
    assert rupees(1_00_000_50) == "Rs 1,00,000.50"
    assert rupees(150_000_00) == "Rs 1,50,000"
    assert rupees(-500_00) == "−Rs 500"
    assert rupees(99) == "Rs 0.99"
