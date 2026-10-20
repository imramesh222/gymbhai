"""Today, reports, and the gym's data in and out (PLAN.md §7)."""

import datetime as dt
import uuid
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, File, Path, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.tenancy import StaffContext, get_in_gym, in_branches
from app.core.calendar import format_bs
from app.core.errors import AppError
from app.core.permissions import Permission
from app.core.time import NEPAL, today_in_nepal, utcnow
from app.db.session import get_db
from app.models.expense import Expense
from app.models.gym import Branch, Gym
from app.models.member import Member
from app.models.member_app import (
    DEVICE_KIOSK,
    REQUEST_PENDING,
    CheckIn,
    Device,
    PaymentRequest,
)
from app.models.membership import SOURCE_IMPORT, Membership, MembershipFreeze
from app.models.payment import Payment
from app.models.platform import MemberImport
from app.models.staff import StaffUser
from app.schemas.reports import (
    ClassesMonthRead,
    ClassTypeMonth,
    ImportCommit,
    ImportPreview,
    InstructorMonth,
    LeadDue,
    MemberBrief,
    MemberOwing,
    MonthlyRead,
    Person,
    PtMonthRead,
    PtTrainerMonth,
    QuietKiosk,
    SetupChecklist,
    TodayRead,
    TrendMonth,
    TrendRead,
)
from app.services import activity, excel, live, reports
from app.services import classes as classes_service
from app.services import expenses as expenses_service
from app.services import leads as leads_service
from app.services import members as members_service
from app.services import memberships as ms

router = APIRouter(tags=["reports and data"])


# --- Today and reports -------------------------------------------------------


# A kiosk asks for its roster every 5 minutes (§19.2): quiet for longer, it
# has lost the internet or been switched off. After 12 hours it's the night.
KIOSK_QUIET = dt.timedelta(minutes=15)
KIOSK_NIGHT = dt.timedelta(hours=12)


def _quiet_kiosks(db: Session, ctx: StaffContext) -> list[QuietKiosk]:
    now = utcnow()
    rows = db.execute(
        in_branches(
            select(Device.name, Branch.name, Device.last_seen_at)
            .join(Branch, Branch.id == Device.branch_id)
            .where(
                Device.gym_id == ctx.gym_id,
                Device.kind == DEVICE_KIOSK,
                Device.revoked_at.is_(None),
                Device.last_seen_at < now - KIOSK_QUIET,
                Device.last_seen_at > now - KIOSK_NIGHT,
            )
            .order_by(Device.last_seen_at),
            Device.branch_id,
            ctx,
        )
    ).all()
    return [QuietKiosk(name=n, branch_name=b, last_seen_at=at) for n, b, at in rows]


@router.get("/dashboard/today", response_model=TodayRead)
def today(
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_VIEW)),
) -> TodayRead:
    """Who's in, who's due, who was turned away, what came in (§7 Today)."""
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    data = reports.today(
        db,
        ctx,
        with_money=ctx.can(Permission.REPORTS_MONEY),
        not_visiting_days=gym.config.not_visiting_days,
    )
    pending = None
    if ctx.can(Permission.PAYMENTS_APPROVE_APP):
        pending = db.scalar(
            select(func.count()).where(
                PaymentRequest.gym_id == ctx.gym_id,
                PaymentRequest.status == REQUEST_PENDING,
            )
        )
    setup = None
    if ctx.can(Permission.SETUP_GYM):
        steps = reports.setup_checklist(db, gym)
        setup = SetupChecklist(**steps) if steps else None
    leads_due, leads_due_list = None, []
    if ctx.can(Permission.LEADS_MANAGE):
        leads_due, rows = leads_service.due(db, ctx, data.date)
        leads_due_list = [
            LeadDue(
                lead_id=r.id,
                name=r.name,
                phone=r.phone,
                status=r.status,
                follow_up_on=r.follow_up_on,  # type: ignore[arg-type]
            )
            for r in rows
        ]
    return TodayRead(
        date=data.date,
        quiet_kiosks=_quiet_kiosks(db, ctx),
        leads_due=leads_due,
        leads_due_list=leads_due_list,
        check_ins=data.check_ins,
        check_ins_by_hour=data.check_ins_by_hour,
        check_ins_yesterday=data.check_ins_yesterday,
        ending_today=[
            MemberBrief(member_id=i, name=n, phone=p) for i, n, p in data.ending_today
        ],
        top_owing=[
            MemberOwing(member_id=i, name=n, dues=d) for i, n, d in data.top_owing
        ],
        unique_visitors=data.unique_visitors,
        inside_now=[Person(member_id=i, name=n, at=at) for i, n, at in data.inside_now],
        due_today=data.due_today,
        expiring_this_week=data.expiring_this_week,
        not_visiting=data.not_visiting,
        turned_away=[
            Person(member_id=i, name=n, at=at, result=r)
            for i, n, r, at in data.expired_but_visiting
        ],
        members_with_dues=data.members_with_dues,
        dues_total=data.dues_total,
        active_members=data.active_members,
        collected=data.collected,
        collected_by_method=data.collected_by_method,
        collected_yesterday=data.collected_yesterday,
        pending_requests=pending,
        setup=setup,
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
    pt = reports.pt_month(db, ctx, data.first_day, data.last_day)
    return MonthlyRead(
        **{**data.__dict__, "renewal_rate": data.renewal_rate, "profit": data.profit},
        personal_training=PtMonthRead(
            income=pt.income,
            sold=pt.sold,
            sessions=pt.sessions,
            members=pt.members,
            by_trainer=[
                PtTrainerMonth(trainer_id=i, name=n, members=m, sessions=s)
                for i, n, m, s in pt.by_trainer
            ],
        )
        if pt
        else None,
        classes=_classes_month(db, ctx, data.first_day, data.last_day),
    )


def _classes_month(
    db: Session, ctx: StaffContext, first: dt.date, last: dt.date
) -> ClassesMonthRead | None:
    found = classes_service.month(
        db,
        ctx,
        reports.day_start(first),
        reports.day_start(last + dt.timedelta(days=1)),
    )
    if found is None:
        return None
    return ClassesMonthRead(
        held=found.held,
        places=found.places,
        booked=found.booked,
        came=found.came,
        no_shows=found.no_shows,
        by_type=[ClassTypeMonth(**t.__dict__) for t in found.by_type],
        by_instructor=[
            InstructorMonth(instructor_id=i, name=n, held=h, came=c)
            for i, n, h, c in found.by_instructor
        ],
    )


@router.get("/reports/trend", response_model=TrendRead)
def trend(
    end: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    months: Annotated[int, Query(ge=2, le=24)] = 12,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.REPORTS_MONEY)),
) -> TrendRead:
    """The last `months` months up to `end`, for the charts on Reports (7.9).

    The same figures as the monthly report, a month at a time: a fixed number
    of queries per month, however large the gym.
    """
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    calendar = "ad" if gym.config.date_display == "ad" else "bs"
    joined = gym.created_at.astimezone(NEPAL).date()
    rows = []
    for month in reports.months_back(end or reports.current_month(calendar), months):
        data = reports.monthly(db, ctx, month)
        rows.append(
            TrendMonth(
                month=month,
                started=data.last_day >= joined,
                income=data.income,
                expenses=data.expenses,
                profit=data.profit,
                new_members=data.new_members,
                renewals=data.renewals,
                lapsed=data.lapsed,
                active_members=data.active_members,
                visits=data.visits,
                renewal_rate=data.renewal_rate,
            )
        )
    return TrendRead(calendar=calendar, months=rows)


# --- export ------------------------------------------------------------------------

EXPORTS = ("members", "memberships", "payments", "expenses", "check-ins")
# Money in and out: for staff who may see money (reports.money).
MONEY_EXPORTS = ("payments", "expenses")


def _staff_names(db: Session, gym_id: uuid.UUID) -> dict[uuid.UUID, str]:
    return dict(
        db.execute(
            select(StaffUser.id, StaffUser.name).where(StaffUser.gym_id == gym_id)
        ).all()
    )


def _local(at: dt.datetime | None) -> str:
    return at.astimezone(NEPAL).strftime("%Y-%m-%d %H:%M") if at else ""


@router.get("/export/{kind}.xlsx")
def export(
    kind: Annotated[
        str, Path(pattern="^(members|memberships|payments|expenses|check-ins)$")
    ],
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_VIEW)),
) -> Response:
    """The gym's data as Excel, any time — even with a lapsed subscription."""
    if kind in MONEY_EXPORTS and not ctx.can(Permission.REPORTS_MONEY):
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
        # Grouped once: filtering the full lists for every row is quadratic.
        payments: dict[uuid.UUID, list[Payment]] = defaultdict(list)
        for p in ms.payments_for(db, [m.id for m in rows_m]):
            payments[p.membership_id].append(p)  # type: ignore[index]
        freezes: dict[uuid.UUID, list[MembershipFreeze]] = defaultdict(list)
        for f in ms.freezes_for(db, [m.id for m in rows_m]):
            freezes[f.membership_id].append(f)
        headers = [
            "Member code", "Member", "Plan", "Branch", *day_headers("Start"),
            *day_headers("End"), "Price (Rs)", "Discount (Rs)", "Admission (Rs)",
            "Total (Rs)", "Paid (Rs)", "Owes (Rs)", "Status", "Source", "Cancel reason",
        ]  # fmt: skip
        rows = []
        for m in rows_m:
            mine = payments[m.id]
            status_now = ms.status_of(m, freezes[m.id])
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
        staff = _staff_names(db, gym.id)
        rows_p = db.scalars(
            select(Payment)
            .where(Payment.gym_id == gym.id, Payment.member_id.in_(by_id))
            .order_by(Payment.receipt_no)
        )
        headers = [
            "Receipt", "Paid at (Nepal time)", "Member code", "Member", "Kind",
            "For", "Amount (Rs)", "Method", "Transaction ID", "Received by",
            "Voided", "Void reason", "Note",
        ]  # fmt: skip
        rows = [
            [
                p.receipt_no,
                _local(p.paid_at),
                by_id[p.member_id].member_code,
                by_id[p.member_id].name,
                p.kind,
                # Personal training is its own money (§18.3).
                "Personal training" if p.pt_package_id else "Membership",
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
    elif kind == "expenses":
        staff = _staff_names(db, gym.id)
        rows_e = db.scalars(
            expenses_service.visible(ctx).order_by(Expense.spent_on, Expense.created_at)
        )
        headers = [
            *day_headers("Date"), "Category", "Amount (Rs)", "Method", "Paid to",
            "Branch", "Note", "Recorded by", "Recorded at (Nepal time)", "Voided",
            "Void reason",
        ]  # fmt: skip
        rows = [
            [
                *day(e.spent_on),
                e.category,
                excel.rupees(e.amount),
                e.method,
                e.paid_to,
                branches.get(e.branch_id) if e.branch_id else "Whole gym",
                e.note,
                staff.get(e.created_by),
                _local(e.created_at),
                bool(e.voided_at),
                e.void_reason,
            ]  # fmt: skip
            for e in rows_e
        ]
    else:
        staff = _staff_names(db, gym.id)
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
    # Locked: a double click on Import must not create everyone twice.
    row = get_in_gym(
        db, MemberImport, import_id, ctx, message="No such import.", for_update=True
    )
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
    skipped = 0
    problems: list[tuple[int, str]] = []
    today = today_in_nepal()
    # Every row checked first, then everyone added in one batch.
    wanted: list[tuple[dict, dict]] = []
    for number, values in enumerate(row.rows, start=1):
        try:
            data = excel.row_to_member(values, mapping)
        except ValueError as exc:
            problems.append((number, str(exc)))
            continue
        key = (data["phone"], data["name"].lower())
        if payload.skip_existing and key in existing:
            skipped += 1
            continue
        membership_fields = {
            k: data.pop(k) for k in ("plan_name", "start_date", "end_date")
        }
        data["home_branch_id"] = branch_id
        data["joined_on"] = data["joined_on"] or today
        wanted.append((data, membership_fields))
        existing.add(key)

    members = members_service.create_many(db, ctx, [d for d, _ in wanted], config)
    for member, (_, membership_fields) in zip(members, wanted, strict=True):
        end = membership_fields["end_date"]
        if end is None:
            continue
        start = membership_fields["start_date"] or min(end, member.joined_on or today)
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
    created = len(members)
    if members:
        # One event for the lot: open dashboards reload their counts once.
        live.publish(db, gym_id=ctx.gym_id, kind=live.MEMBER, branch_id=branch_id)

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
