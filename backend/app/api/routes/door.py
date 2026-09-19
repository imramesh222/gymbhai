"""The door: devices, kiosk scans, staff scans, manual check-in, attendance
(PLAN.md §4.3, §7 Attendance)."""

import datetime as dt
import uuid
from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_device, require
from app.api.routes.member_app import public_gym
from app.api.routes.members import load_member
from app.api.tenancy import StaffContext, for_gym, get_in_gym, in_branches
from app.core.errors import AppError
from app.core.permissions import Permission
from app.core.security import hash_refresh_token, new_refresh_token
from app.core.time import NEPAL, utcnow
from app.db.session import get_db
from app.models.gym import Branch, Gym
from app.models.member import Member
from app.models.member_app import LET_IN, METHOD_MANUAL, CheckIn, Device
from app.models.staff import StaffUser
from app.schemas.member_app import (
    AttendanceSummary,
    CheckInList,
    CheckInRead,
    DeviceIn,
    DeviceRead,
    DeviceRegistered,
    KioskMe,
    ManualCheckIn,
    ScanIn,
    ScanResult,
    StaffScanIn,
)
from app.services import activity, checkins, storage

router = APIRouter(tags=["door"])

DEVICES = require(Permission.SETUP_DEVICES)
CHECK_IN = require(Permission.DOOR_CHECK_IN)


def _branch(db: Session, ctx: StaffContext, branch_id: uuid.UUID) -> Branch:
    return get_in_gym(
        db, Branch, branch_id, ctx, branch_column=Branch.id, message="No such branch."
    )


def scan_result(outcome: checkins.Outcome, *, can_override: bool = False) -> ScanResult:
    state = outcome.state
    return ScanResult(
        result=outcome.check_in.result,
        let_in=outcome.let_in,
        reason=outcome.reason,
        check_in_id=outcome.check_in.id,
        member_id=outcome.member.id,
        member_name=outcome.member.name,
        member_code=outcome.member.member_code,
        photo_url=storage.signed_url(outcome.member.photo_key),
        plan_name=state.current.plan_name if state.current else None,
        days_left=state.days_left,
        valid_until=state.valid_until,
        dues=state.dues,
        can_override=can_override and not outcome.let_in,
    )


UNKNOWN = ScanResult(result="unknown", let_in=False, reason="unknown_code")


# --- devices ---


@router.get("/devices", response_model=list[DeviceRead])
def list_devices(
    db: Session = Depends(get_db), ctx: StaffContext = Depends(DEVICES)
) -> list[Device]:
    stmt = in_branches(for_gym(select(Device), Device, ctx), Device.branch_id, ctx)
    return list(db.scalars(stmt.order_by(Device.created_at.desc())))


@router.post(
    "/devices", response_model=DeviceRegistered, status_code=status.HTTP_201_CREATED
)
def register_device(
    payload: DeviceIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(DEVICES),
) -> DeviceRegistered:
    """ "Use this device as the door scanner for <branch>" (§4.3)."""
    branch = _branch(db, ctx, payload.branch_id)
    token = new_refresh_token()
    device = Device(
        gym_id=ctx.gym_id,
        branch_id=branch.id,
        name=payload.name,
        token_hash=hash_refresh_token(token),
        created_by=ctx.staff.id,
    )
    db.add(device)
    db.flush()
    activity.staff_action(
        db,
        ctx.staff,
        "device.registered",
        entity="device",
        entity_id=device.id,
        changes={"name": device.name, "branch_id": branch.id},
        request=request,
    )
    db.commit()
    return DeviceRegistered(device=DeviceRead.model_validate(device), token=token)


@router.post("/devices/{device_id}/revoke", response_model=DeviceRead)
def revoke_device(
    device_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(DEVICES),
) -> Device:
    device = get_in_gym(
        db,
        Device,
        device_id,
        ctx,
        branch_column=Device.branch_id,
        message="No such device.",
    )
    if device.revoked_at is None:
        device.revoked_at = utcnow()
        activity.staff_action(
            db,
            ctx.staff,
            "device.revoked",
            entity="device",
            entity_id=device.id,
            request=request,
        )
        db.commit()
    return device


# --- the kiosk (device token) ---------------------------------------------------------


@router.get("/kiosk/me", response_model=KioskMe)
def kiosk_me(
    device: Device = Depends(current_device), db: Session = Depends(get_db)
) -> KioskMe:
    gym = db.get(Gym, device.gym_id)
    branch = db.get(Branch, device.branch_id)
    assert gym is not None and branch is not None
    db.commit()  # last_seen_at
    return KioskMe(
        device=DeviceRead.model_validate(device),
        branch_name=branch.name,
        gym=public_gym(db, gym),
    )


@router.post("/kiosk/scan", response_model=ScanResult)
def kiosk_scan(
    payload: ScanIn,
    device: Device = Depends(current_device),
    db: Session = Depends(get_db),
) -> ScanResult:
    gym = db.get(Gym, device.gym_id)
    assert gym is not None
    found = checkins.find_by_code(db, gym.id, payload.code)
    if found is None:
        db.commit()
        return UNKNOWN
    member, method = found
    outcome = checkins.check_in(
        db,
        gym=gym,
        member=member,
        branch_id=device.branch_id,
        method=method,
        device_id=device.id,
    )
    db.commit()
    return scan_result(outcome)


# --- staff at the door ---


@router.post("/check-ins/scan", response_model=ScanResult)
def staff_scan(
    payload: StaffScanIn,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(CHECK_IN),
) -> ScanResult:
    """The scanner button in the staff dashboard (§4.3)."""
    branch = _branch(db, ctx, payload.branch_id)
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    found = checkins.find_by_code(db, ctx.gym_id, payload.code)
    if found is None:
        return UNKNOWN
    member, method = found
    outcome = checkins.check_in(
        db,
        gym=gym,
        member=member,
        branch_id=branch.id,
        method=method,
        staff_id=ctx.staff.id,
    )
    db.commit()
    return scan_result(outcome, can_override=ctx.can(Permission.DOOR_OVERRIDE))


@router.post("/check-ins/manual", response_model=ScanResult)
def manual_check_in(
    payload: ManualCheckIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(CHECK_IN),
) -> ScanResult:
    """A dead phone or a forgotten card; or letting someone in despite a denial."""
    if payload.override and not ctx.can(Permission.DOOR_OVERRIDE):
        raise AppError(
            403,
            "permission_denied",
            "You don't have permission to do this.",
            permission=Permission.DOOR_OVERRIDE.value,
        )
    if payload.override and not payload.note:
        raise AppError(422, "needs_reason", "Say why you are letting them in.")
    member = load_member(db, ctx, payload.member_id)
    branch = _branch(db, ctx, payload.branch_id)
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    outcome = checkins.check_in(
        db,
        gym=gym,
        member=member,
        branch_id=branch.id,
        method=METHOD_MANUAL,
        staff_id=ctx.staff.id,
        override=payload.override,
        note=payload.note,
    )
    if outcome.check_in.result == "override":
        activity.staff_action(
            db,
            ctx.staff,
            "check_in.override",
            entity="member",
            entity_id=member.id,
            changes={"check_in_id": outcome.check_in.id},
            reason=payload.note,
            request=request,
        )
    db.commit()
    return scan_result(outcome, can_override=ctx.can(Permission.DOOR_OVERRIDE))


# --- attendance ---


def _range(date_from: dt.date | None, date_to: dt.date | None):
    conditions = []
    if date_from:
        conditions.append(
            CheckIn.at >= dt.datetime.combine(date_from, dt.time(), tzinfo=NEPAL)
        )
    if date_to:
        end = dt.datetime.combine(
            date_to + dt.timedelta(days=1), dt.time(), tzinfo=NEPAL
        )
        conditions.append(CheckIn.at < end)
    return conditions


@router.get("/check-ins", response_model=CheckInList)
def list_check_ins(
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_VIEW)),
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    member_id: uuid.UUID | None = None,
    denied_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CheckInList:
    conditions = [CheckIn.gym_id == ctx.gym_id, *_range(date_from, date_to)]
    if ctx.branch_ids is not None:
        conditions.append(CheckIn.branch_id.in_(ctx.branch_ids))
    if member_id:
        conditions.append(CheckIn.member_id == member_id)
    if denied_only:
        conditions.append(CheckIn.result.like("denied%"))
    total = db.scalar(select(func.count()).select_from(CheckIn).where(*conditions)) or 0
    rows = db.execute(
        select(CheckIn, Member.name, Member.member_code, StaffUser.name)
        .join(Member, Member.id == CheckIn.member_id)
        .outerjoin(StaffUser, StaffUser.id == CheckIn.staff_user_id)
        .where(*conditions)
        .order_by(CheckIn.at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return CheckInList(
        total=total,
        items=[
            CheckInRead(
                id=c.id,
                at=c.at,
                member_id=c.member_id,
                member_name=name,
                member_code=code,
                branch_id=c.branch_id,
                method=c.method,
                result=c.result,
                staff_name=staff,
                note=c.note,
            )
            for c, name, code, staff in rows
        ],
    )


@router.get("/check-ins/summary", response_model=AttendanceSummary)
def attendance_summary(
    date_from: dt.date,
    date_to: dt.date,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_VIEW)),
) -> AttendanceSummary:
    """Check-ins by day and hour, denied scans and busiest hours (§7)."""
    conditions = [CheckIn.gym_id == ctx.gym_id, *_range(date_from, date_to)]
    if ctx.branch_ids is not None:
        conditions.append(CheckIn.branch_id.in_(ctx.branch_ids))
    rows = db.execute(
        select(CheckIn.at, CheckIn.result, CheckIn.member_id).where(*conditions)
    )
    by_day: Counter[str] = Counter()
    by_hour: Counter[int] = Counter()
    denied = let_in = 0
    members = set()
    for at, result, member_id in rows:
        if result in LET_IN:
            local = at.astimezone(NEPAL)
            by_day[local.date().isoformat()] += 1
            by_hour[local.hour] += 1
            let_in += 1
            members.add(member_id)
        elif result.startswith("denied"):
            denied += 1
    return AttendanceSummary(
        by_day=dict(sorted(by_day.items())),
        by_hour=dict(sorted(by_hour.items())),
        denied=denied,
        let_in=let_in,
        unique_members=len(members),
    )
