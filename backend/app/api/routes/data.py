"""Today, reports, and the gym's data in and out (PLAN.md §7)."""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Path, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.tenancy import StaffContext, get_in_gym
from app.core.calendar import format_bs
from app.core.errors import AppError
from app.core.permissions import Permission
from app.core.time import NEPAL, today_in_nepal, utcnow
from app.db.session import get_db
from app.models.gym import Branch, Gym
from app.models.member import Member
from app.models.member_app import REQUEST_PENDING, CheckIn, PaymentRequest
from app.models.membership import SOURCE_IMPORT, Membership
from app.models.payment import Payment
from app.models.platform import MemberImport
from app.models.staff import StaffUser
from app.schemas.reports import (
    ImportCommit,
    ImportPreview,
    MonthlyRead,
    Person,
    TodayRead,
)
from app.services import activity, excel, reports
from app.services import members as members_service
from app.services import memberships as ms

router = APIRouter(tags=["reports and data"])


# --- Today and reports -------------------------------------------------------


@router.get("/dashboard/today", response_model=TodayRead)
def today(
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_VIEW)),
) -> TodayRead:
    """Who's in, who's due, who was turned away, what came in (§7 Today)."""
    data = reports.today(db, ctx, with_money=ctx.can(Permission.REPORTS_MONEY))
    pending = None
    if ctx.can(Permission.PAYMENTS_APPROVE_APP):
        pending = len(
            db.scalars(
                select(PaymentRequest.id).where(
                    PaymentRequest.gym_id == ctx.gym_id,
                    PaymentRequest.status == REQUEST_PENDING,
                )
            ).all()
        )
    return TodayRead(
        date=data.date,
        check_ins=data.check_ins,
        unique_visitors=data.unique_visitors,
        inside_now=[Person(member_id=i, name=n, at=at) for i, n, at in data.inside_now],
        due_today=data.due_today,
        expiring_this_week=data.expiring_this_week,
        turned_away=[
            Person(member_id=i, name=n, at=at, result=r)
            for i, n, r, at in data.expired_but_visiting
        ],
        members_with_dues=data.members_with_dues,
        dues_total=data.dues_total,
        active_members=data.active_members,
        collected=data.collected,
        collected_by_method=data.collected_by_method,
        pending_requests=pending,
    )


@router.get("/reports/monthly", response_model=MonthlyRead)
def monthly(
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.REPORTS_MONEY)),
) -> MonthlyRead:
    """A month of the gym's own calendar: BS months for a gym showing BS."""
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    calendar = "ad" if gym.config.date_display == "ad" else "bs"
    data = reports.monthly(db, ctx, month or reports.current_month(calendar))
    return MonthlyRead(**{**data.__dict__, "renewal_rate": data.renewal_rate})


# --- export ------------------------------------------------------------------------

EXPORTS = ("members", "memberships", "payments", "check-ins")


def _local(at: dt.datetime | None) -> str:
    return at.astimezone(NEPAL).strftime("%Y-%m-%d %H:%M") if at else ""


@router.get("/export/{kind}.xlsx")
def export(
    kind: Annotated[str, Path(pattern="^(members|memberships|payments|check-ins)$")],
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_VIEW)),
) -> Response:
    """The gym's data as Excel, any time — even with a lapsed subscription."""
    if kind == "payments" and not ctx.can(Permission.REPORTS_MONEY):
        raise AppError(
            403,
            "permission_denied",
            "You don't have permission to do this.",
            permission=Permission.REPORTS_MONEY.value,
        )
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    bs = gym.config.date_display != "ad"
    branches = dict(
        db.execute(select(Branch.id, Branch.name).where(Branch.gym_id == gym.id)).all()
    )
    members = list(db.scalars(members_service.search(ctx).order_by(Member.member_code)))
    archived = list(
        db.scalars(
            members_service.search(ctx, archived=True).order_by(Member.member_code)
        )
    )
    everyone = members + archived
    by_id = {m.id: m for m in everyone}

    def day(value: dt.date | None) -> list[str]:
        if value is None:
            return [""] + ([""] if bs else [])
        return [value.isoformat()] + ([format_bs(value)] if bs else [])

    def day_headers(label: str) -> list[str]:
        return [f"{label} (AD)"] + ([f"{label} (BS)"] if bs else [])

    if kind == "members":
        states = members_service.states_for(db, everyone)
        headers = [
            "Code", "Name", "Phone", "Email", "Gender", *day_headers("Date of birth"),
            "Address", "Emergency contact", "Home branch", *day_headers("Joined"),
            "Status", "Plan", *day_headers("Valid until"), "Days left", "Owes (Rs)",
            "App access", "Archived", "Notes",
        ]  # fmt: skip
        rows = [
            [
                m.member_code,
                m.name,
                m.phone,
                m.email,
                m.gender,
                *day(m.date_of_birth),
                m.address,
                m.emergency_contact,
                branches.get(m.home_branch_id),
                *day(m.joined_on),
                states[m.id].status,
                states[m.id].current.plan_name if states[m.id].current else "",
                *day(states[m.id].valid_until),
                states[m.id].days_left,
                excel.rupees(states[m.id].dues),
                m.app_access,
                m.is_archived,
                m.notes,
            ]  # fmt: skip
            for m in everyone
        ]
    elif kind == "memberships":
        rows_m = list(
            db.scalars(
                select(Membership)
                .where(Membership.member_id.in_(by_id))
                .order_by(Membership.start_date)
            )
        )
        payments = ms.payments_for(db, [m.id for m in rows_m])
        freezes = ms.freezes_for(db, [m.id for m in rows_m])
        headers = [
            "Member code", "Member", "Plan", "Branch", *day_headers("Start"),
            *day_headers("End"), "Price (Rs)", "Discount (Rs)", "Admission (Rs)",
            "Total (Rs)", "Paid (Rs)", "Owes (Rs)", "Status", "Source", "Cancel reason",
        ]  # fmt: skip
        rows = []
        for m in rows_m:
            mine = [p for p in payments if p.membership_id == m.id]
            status_now = ms.status_of(
                m, [f for f in freezes if f.membership_id == m.id]
            )
            rows.append(
                [
                    by_id[m.member_id].member_code,
                    by_id[m.member_id].name,
                    m.plan_name,
                    branches.get(m.branch_id),
                    *day(m.start_date),
                    *day(m.end_date),
                    excel.rupees(m.price),
                    excel.rupees(m.discount),
                    excel.rupees(m.admission_fee),
                    excel.rupees(ms.amount_due(m)),
                    excel.rupees(ms.net_paid(mine)),
                    excel.rupees(ms.dues_of(m, mine)),
                    status_now,
                    m.source,
                    m.cancel_reason,
                ]  # fmt: skip
            )
    elif kind == "payments":
        staff = dict(db.execute(select(StaffUser.id, StaffUser.name)).all())
        rows_p = db.scalars(
            select(Payment)
            .where(Payment.gym_id == gym.id, Payment.member_id.in_(by_id))
            .order_by(Payment.receipt_no)
        )
        headers = [
            "Receipt", "Paid at (Nepal time)", "Member code", "Member", "Kind",
            "Amount (Rs)", "Method", "Transaction ID", "Received by", "Voided",
            "Void reason", "Note",
        ]  # fmt: skip
        rows = [
            [
                p.receipt_no,
                _local(p.paid_at),
                by_id[p.member_id].member_code,
                by_id[p.member_id].name,
                p.kind,
                excel.rupees(p.amount),
                p.method,
                p.transaction_ref,
                staff.get(p.received_by),
                bool(p.voided_at),
                p.void_reason,
                p.note,
            ]  # fmt: skip
            for p in rows_p
        ]
    else:
        staff = dict(db.execute(select(StaffUser.id, StaffUser.name)).all())
        rows_c = db.scalars(
            select(CheckIn)
            .where(CheckIn.gym_id == gym.id, CheckIn.member_id.in_(by_id))
            .order_by(CheckIn.at)
        )
        headers = [
            "At (Nepal time)", "Member code", "Member", "Branch", "Method", "Result",
            "Staff", "Note",
        ]  # fmt: skip
        rows = [
            [
                _local(c.at),
                by_id[c.member_id].member_code,
                by_id[c.member_id].name,
                branches.get(c.branch_id),
                c.method,
                c.result,
                staff.get(c.staff_user_id),
                c.note,
            ]  # fmt: skip
            for c in rows_c
        ]

    activity.staff_action(
        db, ctx.staff, "data.exported", entity="gym", entity_id=gym.id,
        changes={"kind": kind, "rows": len(rows)}, request=request,
    )  # fmt: skip
    db.commit()
    filename = f"{gym.slug}-{kind}-{today_in_nepal().isoformat()}.xlsx"
    return Response(
        content=excel.workbook(kind.title(), headers, rows),
        media_type=excel.XLSX,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- import --------------------------------------------------------------------------

IMPORT = require(Permission.MEMBERS_ADD, Permission.MEMBERSHIPS_SELL)
SAMPLE_ROWS = 20
PROBLEMS_SHOWN = 50


def _preview(row: MemberImport, mapping: dict[str, int | None]) -> ImportPreview:
    problems: list[tuple[int, str]] = []
    ready = 0
    for number, values in enumerate(row.rows, start=1):
        try:
            excel.row_to_member(values, mapping)
            ready += 1
        except ValueError as exc:
            if len(problems) < PROBLEMS_SHOWN:
                problems.append((number, str(exc)))
    return ImportPreview(
        id=row.id,
        filename=row.filename,
        headers=row.headers,
        mapping=mapping,
        total_rows=len(row.rows),
        sample=row.rows[:SAMPLE_ROWS],
        problems=problems,
        ready=ready,
        status=row.status,
        result=row.result,
    )


@router.post(
    "/members/import", response_model=ImportPreview, status_code=status.HTTP_201_CREATED
)
async def upload_register(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(IMPORT),
) -> ImportPreview:
    """Upload an Excel or CSV register: nothing is saved until you commit."""
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise AppError(413, "file_too_large", "Registers must be 10 MB or smaller.")
    headers, rows = excel.read_table(file.filename or "register.xlsx", data)
    mapping = excel.suggest_mapping(headers)
    row = MemberImport(
        gym_id=ctx.gym_id,
        filename=(file.filename or "register")[:255],
        headers=headers,
        rows=rows,
        mapping=mapping,
        created_by=ctx.staff.id,
    )
    db.add(row)
    db.commit()
    return _preview(row, mapping)


@router.post("/members/import/{import_id}/preview", response_model=ImportPreview)
def preview_register(
    import_id: uuid.UUID,
    payload: ImportCommit,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(IMPORT),
) -> ImportPreview:
    """Check a different column mapping before committing."""
    row = get_in_gym(db, MemberImport, import_id, ctx, message="No such import.")
    return _preview(row, payload.mapping or row.mapping or {})


@router.post("/members/import/{import_id}/commit", response_model=ImportPreview)
def commit_register(
    import_id: uuid.UUID,
    payload: ImportCommit,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(IMPORT),
) -> ImportPreview:
    """Create the members, each with their current membership and expiry date.

    Imported memberships carry no price: what members paid before GymBhai is
    not income in GymBhai, and they owe nothing. No SMS is sent; use "Resend
    welcome" when the gym is ready to tell them about the app.
    """
    row = get_in_gym(db, MemberImport, import_id, ctx, message="No such import.")
    if row.status != "preview":
        raise AppError(409, "import_done", "This register has already been imported.")
    mapping = payload.mapping or row.mapping or {}
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    config = gym.config
    branch_id = members_service.default_branch_id(db, ctx)
    existing = {
        (phone, name.lower())
        for phone, name in db.execute(
            select(Member.phone, Member.name).where(Member.gym_id == ctx.gym_id)
        )
    }
    created = skipped = 0
    problems: list[tuple[int, str]] = []
    today = today_in_nepal()
    for number, values in enumerate(row.rows, start=1):
        try:
            data = excel.row_to_member(values, mapping)
        except ValueError as exc:
            problems.append((number, str(exc)))
            continue
        if payload.skip_existing and (data["phone"], data["name"].lower()) in existing:
            skipped += 1
            continue
        membership_fields = {
            k: data.pop(k) for k in ("plan_name", "start_date", "end_date")
        }
        member = members_service.create(
            db,
            ctx,
            {
                **data,
                "home_branch_id": branch_id,
                "joined_on": data["joined_on"] or today,
            },
            config,
        )
        end = membership_fields["end_date"]
        if end is not None:
            start = membership_fields["start_date"] or min(
                end, member.joined_on or today
            )
            db.add(
                Membership(
                    gym_id=ctx.gym_id,
                    member_id=member.id,
                    plan_id=None,
                    plan_name=membership_fields["plan_name"] or "Imported",
                    branch_id=branch_id,
                    start_date=min(start, end),
                    end_date=end,
                    price=0,
                    discount=0,
                    admission_fee=0,
                    created_by=ctx.staff.id,
                    source=SOURCE_IMPORT,
                )
            )
        existing.add((data["phone"], data["name"].lower()))
        created += 1

    row.status = "committed"
    row.mapping = mapping
    row.committed_at = utcnow()
    row.result = {"created": created, "skipped": skipped, "problems": problems[:200]}
    activity.staff_action(
        db,
        ctx.staff,
        "members.imported",
        entity="member_import",
        entity_id=row.id,
        changes=row.result,
        request=request,
    )
    db.commit()
    return _preview(row, mapping)
