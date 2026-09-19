"""Gym sign-up (PLAN.md §1, §5.1, §5.7).

One step creates the gym with its calendar choice, its first branch, the owner
account and a free trial.
"""

import datetime as dt
import re
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.gym_settings import GymSettings
from app.core.security import hash_password
from app.core.time import today_in_nepal
from app.models.billing import SUBSCRIPTION_TRIAL, GymSubscription
from app.models.gym import Branch, Gym
from app.models.plan import DEFAULT_PLANS, Plan
from app.models.staff import StaffUser
from app.schemas.auth import GymSignup
from app.services import activity, reminders
from app.services.sms import service as sms


@dataclass
class Registered:
    gym: Gym
    branch: Branch
    owner: StaffUser
    subscription: GymSubscription


def code_prefix(gym_name: str) -> str:
    """ "Fitness Zone" -> "FZ", "Iron" -> "IRO": the start of every member code."""
    words = [w for w in re.split(r"[^A-Za-z0-9]+", gym_name) if w]
    if len(words) >= 2:
        prefix = "".join(w[0] for w in words[:4])
    else:
        prefix = (words[0] if words else "M")[:3]
    return prefix.upper()


SLUG_TAKEN = AppError(409, "slug_taken", "That gym address is already taken.")
ACCOUNT_EXISTS = AppError(
    409, "account_exists", "An account with that email or phone already exists."
)


def _login_taken(db: Session, email: str | None, phone: str | None) -> bool:
    conditions = []
    if email:
        conditions.append(StaffUser.email == email)
    if phone:
        conditions.append(StaffUser.phone == phone)
    for condition in conditions:
        if db.scalars(select(StaffUser.id).where(condition)).first():
            return True
    return False


def register_gym(
    db: Session, payload: GymSignup, request: Request | None = None
) -> Registered:
    if db.scalars(select(Gym.id).where(Gym.slug == payload.slug)).first():
        raise SLUG_TAKEN
    if _login_taken(db, payload.owner_email, payload.owner_phone):
        raise ACCOUNT_EXISTS

    config = GymSettings(
        plan_months=payload.plan_months,
        date_display=payload.date_display,
        member_code_prefix=code_prefix(payload.gym_name),
    )
    gym = Gym(
        slug=payload.slug,
        name=payload.gym_name,
        phone=payload.owner_phone,
        settings=config.model_dump(),
    )
    db.add(gym)
    try:
        # The checks above are for a friendly message; the unique constraints
        # are what actually stop two sign-ups racing for the same slug.
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise SLUG_TAKEN from exc

    branch = Branch(gym_id=gym.id, name=payload.branch_name)
    owner = StaffUser(
        gym_id=gym.id,
        name=payload.owner_name,
        email=payload.owner_email,
        phone=payload.owner_phone,
        password_hash=hash_password(payload.password),
        is_owner=True,
    )
    today = today_in_nepal()
    subscription = GymSubscription(
        gym_id=gym.id,
        starts_on=today,
        # Inclusive: a 14-day trial started today covers today and 13 more.
        ends_on=today + dt.timedelta(days=settings.trial_days - 1),
        status=SUBSCRIPTION_TRIAL,
    )
    plans = [
        Plan(gym_id=gym.id, name=name, duration_months=months, sort_order=index)
        for index, (name, months) in enumerate(DEFAULT_PLANS)
    ]
    db.add_all([branch, owner, subscription, *plans])
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ACCOUNT_EXISTS from exc

    reminders.seed_rules(db, gym.id)
    if settings.trial_sms_credits:
        sms.add_credits(db, gym.id, settings.trial_sms_credits, "trial")

    activity.staff_action(
        db,
        owner,
        "gym.registered",
        entity="gym",
        entity_id=gym.id,
        changes={
            "slug": gym.slug,
            "branch": branch.name,
            "settings": gym.settings,
            "trial_ends_on": subscription.ends_on,
        },
        request=request,
    )
    return Registered(gym, branch, owner, subscription)
