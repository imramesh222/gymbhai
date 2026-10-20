"""Progress (PLAN.md §19.5): weight and measurements over time, and photos
private to the member unless shared with their trainer."""

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api import idempotency
from app.api.deps import current_member, require
from app.api.presenters import staff_names
from app.api.routes.members import load_member
from app.api.tenancy import StaffContext, get_in_gym
from app.core.errors import not_found
from app.core.permissions import Permission
from app.db.session import get_db
from app.models.member import Member
from app.models.progress import ProgressEntry, ProgressPhoto
from app.schemas.progress import (
    EntryIn,
    EntryRead,
    EntryUpdate,
    HeightIn,
    PhotoRead,
    PhotoUpdate,
    Pose,
    ProgressRead,
)
from app.services import activity, storage
from app.services import progress as service

router = APIRouter(tags=["progress"])
member_router = APIRouter(prefix="/m", tags=["member app"])

RECORD = require(Permission.PROGRESS_RECORD)


def entries_read(db: Session, rows: Sequence[ProgressEntry]) -> list[EntryRead]:
    names = staff_names(db, [r.recorded_by for r in rows])
    reads = []
    for row in rows:
        read = EntryRead.model_validate(row)
        read.recorded_by_name = names.get(row.recorded_by) if row.recorded_by else None
        reads.append(read)
    return reads


def photos_read(rows: Sequence[ProgressPhoto]) -> list[PhotoRead]:
    return [
        PhotoRead(
            id=p.id,
            taken_on=p.taken_on,
            pose=p.pose,
            url=service.photo_url(p),
            shared=p.shared,
        )
        for p in rows
    ]


def progress_read(
    db: Session, member: Member, photos: Sequence[ProgressPhoto]
) -> ProgressRead:
    return ProgressRead(
        height_mm=member.height_mm,
        entries=entries_read(db, service.entries_of(db, member.id)),
        photos=photos_read(photos),
    )


# --- staff -------------------------------------------------------------------------


def _staff_read(db: Session, ctx: StaffContext, member: Member) -> ProgressRead:
    """Photos only if they shared them, and only for their trainer: not even
    the owner, unless the owner trains them."""
    photos = (
        service.photos_of(db, member.id, shared_only=True)
        if service.trains(db, ctx.staff.id, member.id)
        else []
    )
    return progress_read(db, member, photos)


@router.get("/members/{member_id}/progress", response_model=ProgressRead)
def member_progress(
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(RECORD),
) -> ProgressRead:
    return _staff_read(db, ctx, load_member(db, ctx, member_id))


@router.post(
    "/members/{member_id}/progress",
    response_model=ProgressRead,
    status_code=status.HTTP_201_CREATED,
)
def record_progress(
    member_id: uuid.UUID,
    payload: EntryIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(RECORD),
) -> ProgressRead:
    idem = idempotency.begin(db, ctx, request, payload)
    member = load_member(db, ctx, member_id)
    service.record(db, member, payload.model_dump(), staff=ctx.staff)
    answer = _staff_read(db, ctx, member)
    idem.finish(answer)
    db.commit()
    return answer


def _staff_entry(
    db: Session, ctx: StaffContext, entry_id: uuid.UUID
) -> tuple[ProgressEntry, Member]:
    entry = get_in_gym(db, ProgressEntry, entry_id, ctx, message="No such entry.")
    # At a branch the caller works at, as the member's other records.
    return entry, load_member(db, ctx, entry.member_id)


@router.patch("/progress/{entry_id}", response_model=ProgressRead)
def update_progress(
    entry_id: uuid.UUID,
    payload: EntryUpdate,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(RECORD),
) -> ProgressRead:
    entry, member = _staff_entry(db, ctx, entry_id)
    service.update(
        db, member, entry, payload.model_dump(exclude_unset=True), staff=ctx.staff
    )
    db.commit()
    return _staff_read(db, ctx, member)


@router.delete("/progress/{entry_id}", response_model=ProgressRead)
def delete_progress(
    entry_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(RECORD),
) -> ProgressRead:
    entry, member = _staff_entry(db, ctx, entry_id)
    service.remove(db, member, entry, staff=ctx.staff)
    db.commit()
    return _staff_read(db, ctx, member)


@router.put("/members/{member_id}/progress/height", response_model=ProgressRead)
def set_height(
    member_id: uuid.UUID,
    payload: HeightIn,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(RECORD),
) -> ProgressRead:
    member = load_member(db, ctx, member_id)
    member.height_mm = payload.height_mm
    activity.staff_action(
        db, ctx.staff, "progress.height_set", entity="member", entity_id=member.id
    )
    db.commit()
    return _staff_read(db, ctx, member)


# --- the member's own -------------------------------------------------------------


def _mine(db: Session, member: Member) -> ProgressRead:
    return progress_read(db, member, service.photos_of(db, member.id))


@member_router.get("/progress", response_model=ProgressRead)
def my_progress(
    member: Member = Depends(current_member), db: Session = Depends(get_db)
) -> ProgressRead:
    return _mine(db, member)


@member_router.post(
    "/progress", response_model=ProgressRead, status_code=status.HTTP_201_CREATED
)
def record_mine(
    payload: EntryIn,
    request: Request,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> ProgressRead:
    """Once, however often Save is tapped (§17.4)."""
    idem = idempotency.begin_member(db, member, request, payload)
    service.record(db, member, payload.model_dump())
    answer = _mine(db, member)
    idem.finish(answer)
    db.commit()
    return answer


def _own_entry(db: Session, member: Member, entry_id: uuid.UUID) -> ProgressEntry:
    entry = db.get(ProgressEntry, entry_id)
    if entry is None or entry.member_id != member.id:
        raise not_found("No such entry.")
    return entry


@member_router.patch("/progress/{entry_id}", response_model=ProgressRead)
def update_mine(
    entry_id: uuid.UUID,
    payload: EntryUpdate,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> ProgressRead:
    entry = _own_entry(db, member, entry_id)
    service.update(db, member, entry, payload.model_dump(exclude_unset=True))
    db.commit()
    return _mine(db, member)


@member_router.delete("/progress/{entry_id}", response_model=ProgressRead)
def delete_mine(
    entry_id: uuid.UUID,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> ProgressRead:
    service.remove(db, member, _own_entry(db, member, entry_id))
    db.commit()
    return _mine(db, member)


@member_router.put("/progress/height", response_model=ProgressRead)
def set_my_height(
    payload: HeightIn,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> ProgressRead:
    member.height_mm = payload.height_mm
    activity.member_action(db, member, "progress.height_set")
    db.commit()
    return _mine(db, member)


@member_router.post(
    "/progress/photos", response_model=ProgressRead, status_code=status.HTTP_201_CREATED
)
async def add_my_photo(
    pose: Annotated[Pose, Form()],
    taken_on: Annotated[dt.date | None, Form()] = None,
    file: UploadFile = File(...),
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> ProgressRead:
    """Shrunk, and stripped of where and when it was taken."""
    data = await file.read(storage.MAX_BYTES + 1)
    service.add_photo(db, member, data, pose, taken_on)
    db.commit()
    return _mine(db, member)


def _own_photo(db: Session, member: Member, photo_id: uuid.UUID) -> ProgressPhoto:
    photo = db.get(ProgressPhoto, photo_id)
    if photo is None or photo.member_id != member.id:
        raise not_found("No such photo.")
    return photo


@member_router.patch("/progress/photos/{photo_id}", response_model=ProgressRead)
def share_my_photo(
    photo_id: uuid.UUID,
    payload: PhotoUpdate,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> ProgressRead:
    """Let my trainer see it, or stop."""
    photo = _own_photo(db, member, photo_id)
    photo.shared = payload.shared
    activity.member_action(
        db,
        member,
        "progress_photo.shared" if payload.shared else "progress_photo.unshared",
        entity="progress",
        entity_id=photo.id,
    )
    db.commit()
    return _mine(db, member)


@member_router.delete("/progress/photos/{photo_id}", response_model=ProgressRead)
def delete_my_photo(
    photo_id: uuid.UUID,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> ProgressRead:
    key = service.remove_photo(db, member, _own_photo(db, member, photo_id))
    db.commit()
    storage.delete(key)
    return _mine(db, member)
