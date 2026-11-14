"""A gym for testing the phone app (PLAN.md §17.7, 12.9), made fresh each run.

    docker compose exec api python -m scripts.seed_app_test

Removes the gym `e2e-app` if it is there and makes it again, so every Maestro
run (mobile/e2e/) starts from the same place:

- Members with a 1-month membership, paid, ending in 20 days: one for each
  flow (Ram 9800000101, Sita ...103, Maya ...104, Bina ...105, Kiran ...106),
  and Hari and Gita sharing 9800000102 for "Who are you?".
- A priced 1-month plan, an eSewa account to pay, and the join form on.

Members sign in with MASTER_OTP from the root .env, so this is for
development and test databases only; it refuses to run in production.
`scripts.purge_e2e` removes the gym too (its address starts with `e2e-`).
"""

import datetime as dt
import sys

from sqlalchemy import delete, select

import app.models  # noqa: F401  (registers every table)
from app.api.deps import staff_context
from app.core.config import settings
from app.core.time import today_in_nepal
from app.db.base import Base
from app.db.session import SessionLocal
from app.models.gym import Gym
from app.models.payment import GymPaymentMethod
from app.models.plan import Plan
from app.schemas.auth import GymSignup
from app.services import members as members_service
from app.services import memberships as ms
from app.services import registration

SLUG = "e2e-app"
OWNER_PHONE = "9800000100"
# One member per Maestro flow that signs in, so no number reaches the limit
# on codes; Hari and Gita share a phone, for "Who are you?".
MEMBERS = [
    ("Ram Test", "9800000101", True),  # 01 sign in and the QR
    ("Hari Test", "9800000102", True),  # 04 who are you
    ("Gita Test", "9800000102", True),
    ("Sita Test", "9800000103", True),  # 02 renew
    ("Maya Test", "9800000104", True),  # 03 every screen
    ("Bina Test", "9800000105", True),  # 07 sign out
    ("Kiran Test", "9800000106", True),  # 08 offline
]


def remove(db, slug: str) -> None:
    gym = db.scalar(select(Gym).where(Gym.slug == slug))
    if gym is None:
        return
    # Children before parents: sorted_tables is parents first.
    for table in reversed(Base.metadata.sorted_tables):
        if "gym_id" in table.c:
            db.execute(delete(table).where(table.c.gym_id == gym.id))
    db.execute(delete(Gym.__table__).where(Gym.id == gym.id))


def main() -> int:
    if settings.environment == "production":
        print("Not in production: this gym signs in with MASTER_OTP.")
        return 1
    if not settings.master_otp:
        print("Set MASTER_OTP in .env first: the app's tests sign in with it.")
        return 1

    with SessionLocal() as db:
        remove(db, SLUG)
        made = registration.register_gym(
            db,
            GymSignup(
                gym_name="App Test Gym",
                slug=SLUG,
                owner_name="App Test Owner",
                owner_phone=OWNER_PHONE,
                password="app-test-password-123",
                accept_terms=True,
            ),
        )
        gym = made.gym
        gym.settings = {**gym.settings, "plan_months": "bs", "join_form": True}
        plan = db.scalars(
            select(Plan).where(Plan.gym_id == gym.id, Plan.duration_months == 1)
        ).one()
        plan.price = 2500_00
        db.add(
            GymPaymentMethod(
                gym_id=gym.id,
                kind="esewa",
                label="eSewa",
                account_name="App Test Gym",
                account_number="9800000100",
            )
        )
        db.flush()

        ctx = staff_context(made.owner, db)
        today = today_in_nepal()
        for name, phone, paid in MEMBERS:
            member = members_service.create(
                db, ctx, {"name": name, "phone": phone}, gym.config
            )
            if paid:
                ms.sell(
                    db,
                    ctx,
                    member,
                    ms.SaleIn(
                        plan_id=plan.id,
                        start_date=today - dt.timedelta(days=10),
                        end_date=today + dt.timedelta(days=20),
                        payment=ms.PaymentIn(amount=2500_00, method="cash"),
                    ),
                    gym.config,
                )
        db.commit()

    print(f"Gym /{SLUG} is ready. Members:")
    for name, phone, _ in MEMBERS:
        print(f"  {name:<10} {phone}")
    print("Sign in with MASTER_OTP.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
