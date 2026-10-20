"""Progress (PLAN.md §19.5): weight, body fat and measurements, recorded by
the member in their app or by staff who record progress; photos taken in the
app, private to the member unless shared with their trainer.

The activity log says what was done, never the figures: a body's
measurements are the member's own, like a PT session's note (§18.3).
"""

import datetime as dt
import io
import uuid
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.time import today_in_nepal
from app.models.member import Member
from app.models.progress import ProgressEntry, ProgressPhoto
from app.models.staff import StaffUser
from app.models.training import PtPackage
from app.schemas.progress import MEASURES
from app.services import activity, storage

# A phone photo, shrunk: plenty to compare two dates side by side.
PHOTO_SIDE = 1600
PHOTO_QUALITY = 85
OLDEST = dt.date(2000, 1, 1)


def entries_of(db: Session, member_id: uuid.UUID) -> list[ProgressEntry]:
    return list(
        db.scalars(
            select(ProgressEntry)
            .where(ProgressEntry.member_id == member_id)
            .order_by(ProgressEntry.measured_on.desc(), ProgressEntry.created_at.desc())
        )
    )


def photos_of(
    db: Session, member_id: uuid.UUID, *, shared_only: bool = False
) -> list[ProgressPhoto]:
    stmt = select(ProgressPhoto).where(ProgressPhoto.member_id == member_id)
    if shared_only:
        stmt = stmt.where(ProgressPhoto.shared)
    return list(
        db.scalars(stmt.order_by(ProgressPhoto.taken_on.desc(), ProgressPhoto.pose))
    )


def trains(db: Session, staff_id: uuid.UUID, member_id: uuid.UUID) -> bool:
    """Their trainer: a package of theirs, not cancelled, with this trainer.
    Only they see the photos a member shares."""
    return bool(
        db.scalar(
            select(
                exists().where(
                    PtPackage.member_id == member_id,
                    PtPackage.trainer_id == staff_id,
                    PtPackage.cancelled_at.is_(None),
                )
            )
        )
    )


def _day(measured_on: dt.date | None) -> dt.date:
    day = measured_on or today_in_nepal()
    if day > today_in_nepal():
        raise AppError(422, "future_date", "That day hasn't come yet.")
    if day < OLDEST:
        raise AppError(422, "bad_date", "That date is too long ago.")
    return day


def _log(
    db: Session,
    member: Member,
    action: str,
    entity_id: uuid.UUID,
    staff: StaffUser | None,
) -> None:
    """What was done and by whom; no figures."""
    where: dict[str, Any] = {"entity": "progress", "entity_id": entity_id}
    if staff is not None:
        activity.staff_action(
            db, staff, action, changes={"member_id": member.id}, **where
        )
    else:
        activity.member_action(db, member, action, **where)


def record(
    db: Session,
    member: Member,
    fields: dict[str, Any],
    *,
    staff: StaffUser | None = None,
) -> ProgressEntry:
    if member.erased_at is not None:
        raise AppError(409, "member_erased", "This member was erased.")
    entry = ProgressEntry(
        gym_id=member.gym_id,
        member_id=member.id,
        measured_on=_day(fields.pop("measured_on", None)),
        recorded_by=staff.id if staff else None,
        **fields,
    )
    db.add(entry)
    db.flush()
    _log(db, member, "progress.recorded", entry.id, staff)
    return entry


def may_change(entry: ProgressEntry, *, staff: StaffUser | None) -> None:
    """The member changes any of theirs; staff, what staff recorded."""
    if staff is not None and entry.recorded_by is None:
        raise AppError(
            403,
            "members_own",
            "The member recorded this one in their app: only they can change it.",
        )


def update(
    db: Session,
    member: Member,
    entry: ProgressEntry,
    changes: dict[str, Any],
    *,
    staff: StaffUser | None = None,
) -> ProgressEntry:
    may_change(entry, staff=staff)
    if "measured_on" in changes:
        changes["measured_on"] = _day(changes["measured_on"])
    for key, value in changes.items():
        setattr(entry, key, value)
    if all(getattr(entry, m) is None for m in MEASURES):
        raise AppError(422, "nothing_measured", "Enter a weight or a measurement.")
    _log(db, member, "progress.updated", entry.id, staff)
    return entry


def remove(
    db: Session,
    member: Member,
    entry: ProgressEntry,
    *,
    staff: StaffUser | None = None,
) -> None:
    may_change(entry, staff=staff)
    _log(db, member, "progress.deleted", entry.id, staff)
    db.delete(entry)


# --- photos ----------------------------------------------------------------------


def shrink(data: bytes) -> bytes:
    """A JPEG at most PHOTO_SIDE on its long side, the right way up, with
    nothing else of the original: no location, no camera, no date."""
    storage.sniff_image(data)  # size and type, as for every upload
    try:
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image)
    except (UnidentifiedImageError, OSError) as exc:
        raise AppError(
            415, "unsupported_image", "Upload a JPEG, PNG or WebP image."
        ) from exc
    image = image.convert("RGB")
    image.thumbnail((PHOTO_SIDE, PHOTO_SIDE))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=PHOTO_QUALITY, optimize=True)
    return out.getvalue()


def add_photo(
    db: Session, member: Member, data: bytes, pose: str, taken_on: dt.date | None
) -> ProgressPhoto:
    key = storage.put(storage.new_key(member.gym_id, "progress", "jpg"), shrink(data))
    photo = ProgressPhoto(
        gym_id=member.gym_id,
        member_id=member.id,
        taken_on=_day(taken_on),
        pose=pose,
        photo_key=key,
    )
    db.add(photo)
    db.flush()
    _log(db, member, "progress_photo.added", photo.id, None)
    return photo


def remove_photo(db: Session, member: Member, photo: ProgressPhoto) -> str:
    """Returns the stored file, to delete once the transaction commits."""
    _log(db, member, "progress_photo.deleted", photo.id, None)
    key = photo.photo_key
    db.delete(photo)
    return key


# Photos are private: a link that lasts long enough to look, no longer.
PHOTO_LINK_SECONDS = 15 * 60


def photo_url(photo: ProgressPhoto) -> str:
    url = storage.signed_url(photo.photo_key, ttl=PHOTO_LINK_SECONDS)
    assert url is not None
    return url
