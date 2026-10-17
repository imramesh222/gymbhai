"""Gyms sending us gyms (PLAN.md §16.5, 10.5).

An owner shares /signup?ref=<their gym's address>. The new gym is linked at
sign-up. When its first subscription payment is approved, the referral is
ready, and in /admin we give both gyms a free month (or don't, with a note).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.time import utcnow
from app.models.billing import SUBSCRIPTION_ACTIVE, GymSubscription
from app.models.gym import GYM_ACTIVE, Gym
from app.models.platform import (
    REFERRAL_PENDING,
    REFERRAL_READY,
    REFERRAL_REJECTED,
    REFERRAL_REWARDED,
    GymReferral,
)
from app.models.staff import StaffUser
from app.services import subscription

FREE_MONTHS = 1


def link(gym: Gym) -> str:
    return f"{settings.public_app_url.rstrip('/')}/signup?ref={gym.slug}"


def on_signup(db: Session, new_gym: Gym, ref: str | None) -> None:
    """Link the new gym to the one that sent it. A wrong code is ignored:
    signing up must never fail over a referral."""
    if not ref:
        return
    referrer = db.scalar(
        select(Gym).where(Gym.slug == ref.strip().lower(), Gym.status == GYM_ACTIVE)
    )
    if referrer is None or referrer.id == new_gym.id:
        return
    db.add(GymReferral(gym_id=referrer.id, referred_gym_id=new_gym.id))


def on_first_payment(db: Session, gym_id: uuid.UUID) -> None:
    """The referred gym paid: ready to reward (once)."""
    row = db.scalar(
        select(GymReferral).where(
            GymReferral.referred_gym_id == gym_id,
            GymReferral.status == REFERRAL_PENDING,
        )
    )
    if row is not None:
        row.status = REFERRAL_READY
        row.ready_at = utcnow()


def _paid_plan(db: Session, gym_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(
        select(GymSubscription.platform_plan_id)
        .where(
            GymSubscription.gym_id == gym_id,
            GymSubscription.status == SUBSCRIPTION_ACTIVE,
        )
        .order_by(GymSubscription.ends_on.desc())
        .limit(1)
    )


def reward(db: Session, row: GymReferral, admin: StaffUser) -> list[Gym]:
    """A free month for both: on top of what each has, on its current plan."""
    if row.status != REFERRAL_READY:
        raise AppError(409, "not_ready", "This referral isn't ready to reward.")
    gyms = [db.get(Gym, row.gym_id), db.get(Gym, row.referred_gym_id)]
    for gym in gyms:
        assert gym is not None
        subscription.extend(
            db, gym.id, platform_plan_id=_paid_plan(db, gym.id), months=FREE_MONTHS
        )
    row.status = REFERRAL_REWARDED
    row.reviewed_at = utcnow()
    row.reviewed_by = admin.id
    return gyms  # type: ignore[return-value]


def reject(db: Session, row: GymReferral, admin: StaffUser, note: str) -> None:
    if row.status not in (REFERRAL_PENDING, REFERRAL_READY):
        raise AppError(409, "not_ready", "This referral has been dealt with.")
    row.status = REFERRAL_REJECTED
    row.note = note
    row.reviewed_at = utcnow()
    row.reviewed_by = admin.id
