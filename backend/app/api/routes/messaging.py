"""Expiry lists, SMS, reminder rules and notices (PLAN.md §7, §9)."""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.presenters import member_read
from app.api.routes.members import load_member
from app.api.tenancy import StaffContext, for_gym, get_in_gym
from app.core.errors import AppError
from app.core.gym_settings import GymSettings
from app.core.permissions import Permission
from app.core.sms_text import segments
from app.core.time import today_in_nepal, utcnow
from app.db.session import get_db
from app.models.gym import Gym
from app.models.member import Member
from app.models.membership import Membership
from app.models.messaging import (
    SMS_MANUAL,
    SMS_NOTICE,
    Notice,
    ReminderRule,
    SmsMessage,
)
from app.schemas.messaging import (
    ExpiringLists,
    MemberSmsIn,
    NoticeCost,
    NoticeIn,
    NoticeRead,
    ReminderRuleIn,
    ReminderRuleRead,
    ReminderRuleUpdate,
    SmsLog,
    SmsRead,
    SmsTemplates,
    SmsTemplatesUpdate,
)
from app.services import activity, reminders
from app.services import members as members_service
from app.services.sms import service as sms

router = APIRouter(tags=["messages"])

LAPSED_DAYS = 30
WEEK = 7


def _gym(db: Session, ctx: StaffContext) -> Gym:
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    return gym


# --- the Expiring list ----------------------------------------------------------


@router.get("/lists/expiring", response_model=ExpiringLists)
def expiring(
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_VIEW)),
) -> ExpiringLists:
    """Who to chase today: ending this week, ending today, lapsed this month."""
    today = today_in_nepal()
    stmt = (
        select(Member)
        .join(Membership, Membership.member_id == Member.id)
        .where(
            Member.gym_id == ctx.gym_id,
            Member.is_archived.is_(False),
            Membership.cancelled_at.is_(None),
            Membership.end_date >= today - dt.timedelta(days=LAPSED_DAYS),
            Membership.end_date <= today + dt.timedelta(days=WEEK),
        )
        .distinct()
    )
    if ctx.branch_ids is not None:
        stmt = stmt.where(Member.home_branch_id.in_(ctx.branch_ids))
    members = list(db.scalars(stmt))
    states = members_service.states_for(db, members, today)

    lists = ExpiringLists(due_today=[], due_this_week=[], lapsed=[])
    for member in sorted(members, key=lambda m: (states[m.id].valid_until, m.name)):
        state = states[member.id]
        end = state.valid_until
        if end is None:
            continue
        item = member_read(member, state)
        if end == today:
            lists.due_today.append(item)
        elif today < end <= today + dt.timedelta(days=WEEK):
            lists.due_this_week.append(item)
        elif today - dt.timedelta(days=LAPSED_DAYS) <= end < today:
            lists.lapsed.append(item)
    lists.lapsed.reverse()  # most recently lapsed first
    return lists


# --- SMS --------------------------------------------------------------------------


@router.get("/sms", response_model=SmsLog)
def sms_log(
    member_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MESSAGES_SMS)),
) -> SmsLog:
    stmt = for_gym(select(SmsMessage), SmsMessage, ctx)
    if member_id is not None:
        stmt = stmt.where(SmsMessage.member_id == member_id)
    rows = db.scalars(stmt.order_by(SmsMessage.created_at.desc()).limit(limit))
    return SmsLog(
        balance=sms.balance(db, ctx.gym_id),
        items=[SmsRead.model_validate(r) for r in rows],
    )


@router.post(
    "/members/{member_id}/sms",
    response_model=SmsRead,
    status_code=status.HTTP_201_CREATED,
)
def sms_member(
    member_id: uuid.UUID,
    payload: MemberSmsIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MESSAGES_SMS)),
) -> SmsMessage:
    """A one-off SMS, or "Send reminder now" from the Expiring list."""
    member = load_member(db, ctx, member_id)
    gym = _gym(db, ctx)
    body = (
        reminders.reminder_text(db, gym, member) if payload.reminder else payload.body
    )
    assert body is not None
    message = sms.queue(
        db,
        gym_id=ctx.gym_id,
        to=member.phone,
        body=body,
        kind="reminder" if payload.reminder else SMS_MANUAL,
        member_id=member.id,
        created_by=ctx.staff.id,
    )
    activity.staff_action(
        db,
        ctx.staff,
        "sms.sent",
        entity="member",
        entity_id=member.id,
        changes={"sms_id": message.id, "reminder": payload.reminder},
        request=request,
    )
    db.commit()
    return message


# --- reminder rules and wording -----------------------------------------------------

SETUP_REMINDERS = require(Permission.SETUP_REMINDERS)
RULE_TAKEN = AppError(409, "rule_exists", "There is already a reminder for that day.")


@router.get("/reminder-rules", response_model=list[ReminderRuleRead])
def list_rules(
    db: Session = Depends(get_db), ctx: StaffContext = Depends(SETUP_REMINDERS)
) -> list[ReminderRule]:
    stmt = for_gym(select(ReminderRule), ReminderRule, ctx)
    return list(db.scalars(stmt.order_by(ReminderRule.days_from_expiry)))


@router.post(
    "/reminder-rules",
    response_model=ReminderRuleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_rule(
    payload: ReminderRuleIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SETUP_REMINDERS),
) -> ReminderRule:
    rule = ReminderRule(gym_id=ctx.gym_id, **payload.model_dump())
    db.add(rule)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise RULE_TAKEN from exc
    activity.staff_action(
        db,
        ctx.staff,
        "reminder_rule.created",
        entity="reminder_rule",
        entity_id=rule.id,
        changes=payload.model_dump(),
        request=request,
    )
    db.commit()
    return rule


@router.patch("/reminder-rules/{rule_id}", response_model=ReminderRuleRead)
def update_rule(
    rule_id: uuid.UUID,
    payload: ReminderRuleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SETUP_REMINDERS),
) -> ReminderRule:
    rule = get_in_gym(db, ReminderRule, rule_id, ctx, message="No such reminder.")
    fields = ("days_from_expiry", "template", "enabled")
    before = {f: getattr(rule, f) for f in fields}
    for name, value in payload.model_dump(
        exclude_unset=True, exclude_none=True
    ).items():
        setattr(rule, name, value)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise RULE_TAKEN from exc
    diff = activity.diff(before, {f: getattr(rule, f) for f in fields})
    if diff:
        activity.staff_action(
            db,
            ctx.staff,
            "reminder_rule.updated",
            entity="reminder_rule",
            entity_id=rule.id,
            changes=diff,
            request=request,
        )
    db.commit()
    return rule


@router.delete("/reminder-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SETUP_REMINDERS),
) -> Response:
    rule = get_in_gym(db, ReminderRule, rule_id, ctx, message="No such reminder.")
    activity.staff_action(
        db,
        ctx.staff,
        "reminder_rule.deleted",
        entity="reminder_rule",
        entity_id=rule.id,
        changes={"days_from_expiry": rule.days_from_expiry, "template": rule.template},
        request=request,
    )
    db.delete(rule)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sms-templates", response_model=SmsTemplates)
def get_templates(
    db: Session = Depends(get_db), ctx: StaffContext = Depends(SETUP_REMINDERS)
) -> SmsTemplates:
    config = _gym(db, ctx).config
    return SmsTemplates(
        welcome_sms=config.welcome_sms, membership_sms=config.membership_sms
    )


@router.patch("/sms-templates", response_model=SmsTemplates)
def update_templates(
    payload: SmsTemplatesUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SETUP_REMINDERS),
) -> SmsTemplates:
    gym = _gym(db, ctx)
    before = dict(gym.settings)
    update = payload.model_dump(exclude_unset=True, exclude_none=True)
    gym.settings = GymSettings.model_validate({**gym.settings, **update}).model_dump()
    diff = activity.diff(before, gym.settings)
    if diff:
        activity.staff_action(
            db,
            ctx.staff,
            "gym.sms_templates_updated",
            entity="gym",
            entity_id=gym.id,
            changes=diff,
            request=request,
        )
    db.commit()
    return SmsTemplates(
        welcome_sms=gym.config.welcome_sms, membership_sms=gym.config.membership_sms
    )


# --- notices ---------------------------------------------------------------------

NOTICES = require(Permission.MESSAGES_NOTICES)


def notice_recipients(
    db: Session, ctx: StaffContext, branch_id: uuid.UUID | None
) -> list[Member]:
    """Members with a current or upcoming membership, and the app turned on."""
    today = today_in_nepal()
    stmt = (
        select(Member)
        .join(Membership, Membership.member_id == Member.id)
        .where(
            Member.gym_id == ctx.gym_id,
            Member.is_archived.is_(False),
            Member.app_access.is_(True),
            Membership.cancelled_at.is_(None),
            Membership.end_date >= today,
        )
        .distinct()
    )
    if branch_id is not None:
        stmt = stmt.where(Member.home_branch_id == branch_id)
    elif ctx.branch_ids is not None:
        stmt = stmt.where(Member.home_branch_id.in_(ctx.branch_ids))
    return list(db.scalars(stmt))


def _notice_sms(gym: Gym, title: str, body: str) -> str:
    return f"{gym.name}: {title}\n{body}"


@router.get("/notices", response_model=list[NoticeRead])
def list_notices(
    db: Session = Depends(get_db), ctx: StaffContext = Depends(NOTICES)
) -> list[Notice]:
    stmt = for_gym(select(Notice), Notice, ctx)
    return list(db.scalars(stmt.order_by(Notice.published_at.desc()).limit(100)))


@router.post("/notices/cost", response_model=NoticeCost)
def notice_cost(
    payload: NoticeIn,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(NOTICES),
) -> NoticeCost:
    """What sending this notice by SMS would cost, before sending it (§7)."""
    gym = _gym(db, ctx)
    count = len(notice_recipients(db, ctx, payload.branch_id))
    each = segments(_notice_sms(gym, payload.title, payload.body))
    return NoticeCost(
        recipients=count,
        segments_each=each,
        total_credits=count * each,
        balance=sms.balance(db, ctx.gym_id),
    )


@router.post("/notices", response_model=NoticeRead, status_code=status.HTTP_201_CREATED)
def create_notice(
    payload: NoticeIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(NOTICES),
) -> Notice:
    if payload.branch_id is not None and not ctx.can_access_branch(payload.branch_id):
        raise AppError(403, "branch_denied", "You don't work at that branch.")
    gym = _gym(db, ctx)
    notice = Notice(
        gym_id=ctx.gym_id,
        branch_id=payload.branch_id,
        title=payload.title,
        body=payload.body,
        send_sms=payload.send_sms,
        published_at=utcnow(),
        created_by=ctx.staff.id,
    )
    db.add(notice)
    db.flush()
    if payload.send_sms:
        if not ctx.can(Permission.MESSAGES_SMS):
            raise AppError(
                403,
                "permission_denied",
                "You don't have permission to do this.",
                permission=Permission.MESSAGES_SMS.value,
            )
        text = _notice_sms(gym, payload.title, payload.body)
        for member in notice_recipients(db, ctx, payload.branch_id):
            sms.queue(
                db,
                gym_id=ctx.gym_id,
                to=member.phone,
                body=text,
                kind=SMS_NOTICE,
                member_id=member.id,
                created_by=ctx.staff.id,
            )
            notice.sms_count += 1
    activity.staff_action(
        db,
        ctx.staff,
        "notice.published",
        entity="notice",
        entity_id=notice.id,
        changes={"title": notice.title, "sms_count": notice.sms_count},
        request=request,
    )
    db.commit()
    return notice


@router.delete("/notices/{notice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notice(
    notice_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(NOTICES),
) -> Response:
    """Takes it off the member app. SMS already sent stay sent."""
    notice = get_in_gym(db, Notice, notice_id, ctx, message="No such notice.")
    activity.staff_action(
        db,
        ctx.staff,
        "notice.deleted",
        entity="notice",
        entity_id=notice.id,
        changes={"title": notice.title},
        request=request,
    )
    db.delete(notice)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
