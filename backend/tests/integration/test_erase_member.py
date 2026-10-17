"""Erasing a member at their request (PLAN.md §16.1, step 6.8)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import Permission
from app.models.activity import ActivityLog
from app.models.member import Member
from app.models.member_app import (
    METHOD_MANUAL,
    CheckIn,
    MemberSession,
    OtpCode,
    PaymentRequest,
)
from app.models.membership import Membership
from app.models.messaging import SmsMessage
from app.models.payment import Payment
from app.models.platform import MemberImport
from app.models.staff import StaffUser
from app.services import checkins, member_auth, storage
from app.services.members import ERASED_NAME, ERASED_PHONE
from tests.conftest import GymFixture, make_member, sell, sign_in

PHONE = "9812345678"


@pytest.fixture(autouse=True)
def files_in_a_scratch_folder(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "media_root", str(tmp_path))


def erase(client: TestClient, member: Member):
    return client.post(f"/api/v1/members/{member.id}/erase")


def count(db: Session, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where))


def a_member_with_history(db: Session, gym: GymFixture) -> Member:
    """Details, a sale, a payment, a check-in, an SMS, a session, a code,
    a payment screenshot and a register row: everywhere their details go."""
    member = make_member(db, gym, name="Sita Rai", phone=PHONE)
    member.email = "sita@example.com"
    member.address = "Baneshwor"
    member.notes = "Bad knee"
    member.photo_key = storage.put(f"{gym.gym.id}/members/sita.png", b"png")
    membership, _ = sell(db, gym, member, paid=1500_00)
    checkins.check_in(
        db,
        gym=gym.gym,
        member=member,
        branch_id=gym.branch.id,
        method=METHOD_MANUAL,
    )
    db.add_all(
        [
            SmsMessage(
                gym_id=gym.gym.id,
                member_id=member.id,
                to=PHONE,
                body="Hi Sita, your membership ends soon",
                kind="reminder",
                segments=1,
            ),
            SmsMessage(
                gym_id=gym.gym.id,
                to=PHONE,
                body=member_auth.REDACTED,
                kind="otp",
                segments=1,
            ),
            PaymentRequest(
                gym_id=gym.gym.id,
                member_id=member.id,
                plan_id=membership.plan_id,
                amount=1500_00,
                screenshot_key=storage.put(f"{gym.gym.id}/proof/sita.png", b"png"),
            ),
            MemberImport(
                gym_id=gym.gym.id,
                filename="register.csv",
                headers=["Name", "Mobile"],
                rows=[["Sita Rai", "+977 981-2345678"], ["Hari Thapa", "9841111111"]],
            ),
        ]
    )
    member_auth.start_session(db, member, None)
    db.commit()
    return member


def test_the_owner_erases_a_member(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = a_member_with_history(db, gym_a)
    photo = member.photo_key
    screenshot = db.scalars(select(PaymentRequest.screenshot_key)).one()
    sign_in(db, client, gym_a.owner)
    response = erase(client, member)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == ERASED_NAME
    assert body["erased_at"] is not None
    assert body["email"] is None and body["notes"] is None

    db.refresh(member)
    assert (member.phone, member.address, member.photo_key) == (
        ERASED_PHONE,
        None,
        None,
    )
    assert not member.app_access and member.is_archived
    assert storage.read(photo) is None  # type: ignore[arg-type]
    assert storage.read(screenshot) is None  # type: ignore[arg-type]


def test_their_traces_go_and_the_accounts_stay(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = a_member_with_history(db, gym_a)
    sign_in(db, client, gym_a.owner)
    erase(client, member)

    assert count(db, MemberSession, MemberSession.member_id == member.id) == 0
    assert count(db, SmsMessage, SmsMessage.to == PHONE) == 0
    bodies = db.scalars(
        select(SmsMessage.body).where(SmsMessage.member_id == member.id)
    ).all()
    assert bodies == ["(erased)"]
    assert count(db, OtpCode, OtpCode.destination == PHONE) == 0
    request = db.scalars(select(PaymentRequest)).one()
    assert request.screenshot_key is None
    upload = db.scalars(select(MemberImport)).one()
    assert upload.rows == [["Hari Thapa", "9841111111"]]
    history = db.scalars(
        select(ActivityLog).where(
            ActivityLog.entity == "member", ActivityLog.entity_id == member.id
        )
    ).all()
    assert all(entry.changes is None for entry in history)
    assert "member.erased" in [entry.action for entry in history]

    # The gym's accounts: untouched.
    assert count(db, Membership, Membership.member_id == member.id) == 1
    assert count(db, Payment, Payment.member_id == member.id) == 1
    assert count(db, CheckIn, CheckIn.member_id == member.id) == 1


def test_a_shared_family_number_keeps_working(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    """A parent and child on one phone: erasing one leaves the other's sign-in."""
    member = a_member_with_history(db, gym_a)
    sibling = make_member(db, gym_a, name="Ram Rai", phone=PHONE)
    db.add(
        OtpCode(
            gym_id=gym_a.gym.id,
            channel="sms",
            destination=PHONE,
            code_hash="x" * 64,
            expires_at=member.created_at,
        )
    )
    db.commit()
    sign_in(db, client, gym_a.owner)
    erase(client, member)
    assert count(db, OtpCode, OtpCode.destination == PHONE) == 1
    db.refresh(sibling)
    assert sibling.phone == PHONE
    upload = db.scalars(select(MemberImport)).one()
    assert len(upload.rows) == 2


def test_an_erased_member_cant_be_changed_or_contacted(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = a_member_with_history(db, gym_a)
    sign_in(db, client, gym_a.owner)
    erase(client, member)
    for response in (
        erase(client, member),
        client.post(f"/api/v1/members/{member.id}/unarchive"),
        client.patch(f"/api/v1/members/{member.id}", json={"name": "Sita"}),
        client.post(f"/api/v1/members/{member.id}/resend-welcome"),
        client.post(f"/api/v1/members/{member.id}/sms", json={"body": "Hello"}),
    ):
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "member_erased"


def test_only_the_owner_can_erase(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    member = make_member(db, gym_a)
    manager = make_staff(gym_a.gym, permissions=[p.value for p in Permission])
    sign_in(db, client, manager)
    response = erase(client, member)
    assert response.status_code == 403
    assert response.json()["code"] == "owner_only"
