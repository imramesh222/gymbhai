"""The signed-in user's own gym (PLAN.md §8, Setup)."""

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.tenancy import StaffContext
from app.core.errors import not_found
from app.core.gym_settings import GymSettings
from app.core.permissions import Permission
from app.db.session import get_db
from app.models.gym import Gym
from app.schemas.auth import GymRead
from app.schemas.gym import CheckInRulesUpdate, GymUpdate
from app.services import activity, storage

router = APIRouter(prefix="/gym", tags=["gym"])

EDITABLE = ("name", "phone", "address", "brand_color")


def _own_gym(db: Session, ctx: StaffContext) -> Gym:
    gym = db.get(Gym, ctx.gym_id)
    if gym is None:
        raise not_found("Gym not found.")
    return gym


def gym_read(gym: Gym) -> GymRead:
    read = GymRead.model_validate(gym)
    read.logo_url = storage.signed_url(gym.logo_key)
    return read


@router.get("", response_model=GymRead)
def get_gym(
    db: Session = Depends(get_db), ctx: StaffContext = Depends(require())
) -> GymRead:
    return gym_read(_own_gym(db, ctx))


@router.patch("", response_model=GymRead)
def update_gym(
    payload: GymUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.SETUP_GYM)),
) -> GymRead:
    """Gym profile and calendar settings.

    Changing how plan months are counted only affects memberships sold after
    the change; existing end dates are stored and never recomputed (§5.1).
    """
    gym = _own_gym(db, ctx)
    before = {field: getattr(gym, field) for field in EDITABLE}
    before["settings"] = dict(gym.settings)

    changes = payload.model_dump(exclude_unset=True, exclude={"settings"})
    for field, value in changes.items():
        setattr(gym, field, value)
    if payload.settings is not None:
        # A null setting means "unchanged", never "unset": most are required.
        update = payload.settings.model_dump(exclude_unset=True, exclude_none=True)
        merged = {**gym.settings, **update}
        gym.settings = GymSettings.model_validate(merged).model_dump()

    after = {field: getattr(gym, field) for field in EDITABLE}
    after["settings"] = dict(gym.settings)
    diff = activity.diff(before, after)
    if diff:
        activity.staff_action(
            db,
            ctx.staff,
            "gym.updated",
            entity="gym",
            entity_id=gym.id,
            changes=diff,
            request=request,
        )
    db.commit()
    db.refresh(gym)
    return gym_read(gym)


@router.patch("/check-in-rules", response_model=GymRead)
def update_check_in_rules(
    payload: CheckInRulesUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.SETUP_CHECK_IN_RULES)),
) -> GymRead:
    """Dues rule, grace days and the re-scan window at the door."""
    gym = _own_gym(db, ctx)
    before = dict(gym.settings)
    update = payload.model_dump(exclude_unset=True, exclude_none=True)
    gym.settings = GymSettings.model_validate({**gym.settings, **update}).model_dump()
    diff = activity.diff(before, gym.settings)
    if diff:
        activity.staff_action(
            db,
            ctx.staff,
            "gym.check_in_rules_updated",
            entity="gym",
            entity_id=gym.id,
            changes=diff,
            request=request,
        )
    db.commit()
    db.refresh(gym)
    return gym_read(gym)


@router.post("/logo", response_model=GymRead)
async def upload_logo(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.SETUP_GYM)),
) -> GymRead:
    gym = _own_gym(db, ctx)
    data = await file.read(storage.MAX_BYTES + 1)
    key = storage.put(
        storage.new_key(ctx.gym_id, "logo", storage.sniff_image(data)), data
    )
    old = gym.logo_key
    gym.logo_key = key
    activity.staff_action(
        db,
        ctx.staff,
        "gym.logo_changed",
        entity="gym",
        entity_id=gym.id,
        changes={"logo_key": {"before": old, "after": key}},
        request=request,
    )
    db.commit()
    storage.delete(old)
    return gym_read(gym)
