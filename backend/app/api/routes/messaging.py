"""Expiry lists, SMS, reminder rules and notices (PLAN.md §7, §9)."""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.presenters import member_read
from app.api.routes.members import load_member
from app.api.tenancy import StaffContext, for_gym, get_in_gym
from app.core.errors import AppError, not_found
from app.core.gym_settings import GymSettings
from app.core.permissions import Permission
from app.core.sms_text import segments
from app.core.time import today_in_nepal, utcnow
from app.core.whatsapp_templates import TEMPLATES, for_rule, meta_language
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
from app.models.staff import StaffUser
from app.models.training import PtPackage
from app.schemas.messaging import (
    BulkSmsIn,
    BulkSmsResult,
    FollowUpLists,
    MemberMessage,
    MemberSmsIn,
    MessagePurpose,
    NoticeCost,
    NoticeIn,
    NoticeRead,
    PtOwing,
    ReminderRuleIn,
    ReminderRuleRead,
    ReminderRuleUpdate,
    SmsLog,
    SmsRead,
    SmsTemplates,
    SmsTemplatesUpdate,
    check_days,
)
from app.services import activity, live, reminders, training
from app.services import members as members_service
from app.services.push import service as push
from app.services.sms import service as sms
from app.services.whatsapp import service as whatsapp

router = APIRouter(tags=["messages"])

LAPSED_DAYS = 30
WEEK = 7


def _gym(db: Session, ctx: StaffContext) -> Gym:
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    return gym


# --- Follow up --------------------------------------------------------------------

FOLLOW_UP_SHOWN = 100


@router.get("/lists/follow-up", response_model=FollowUpLists)
def follow_up(
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_VIEW)),
) -> FollowUpLists:
    """Who to chase (PLAN.md §16.3, 8.1): ending today or this week, lapsed in
    the last 30 days, owing money (and on personal training, §18.3), and
    active but not visiting."""
    today = today_in_nepal()
    days = _gym(db, ctx).config.not_visiting_days
    ending = list(
        db.scalars(
            members_service.search(ctx, today=today).where(
                Member.id.in_(
                    select(Membership.member_id).where(
                        Membership.gym_id == ctx.gym_id,
                        Membership.cancelled_at.is_(None),
                        Membership.end_date >= today - dt.timedelta(days=LAPSED_DAYS),
                        Membership.end_date <= today + dt.timedelta(days=WEEK),
                    )
                )
            )
        )
    )
    dues = members_service.dues_expression()
    owing_stmt = members_service.search(ctx, today=today).where(dues > 0)
    owing = list(
        db.scalars(owing_stmt.order_by(dues.desc(), Member.name).limit(FOLLOW_UP_SHOWN))
    )
    # Personal training owed, at the branches the caller works at (§18.3).
    pt_owed = training.dues_expression()
    pt_owing_stmt = (
        training.visible(ctx)
        .join(Member, Member.id == PtPackage.member_id)
        .where(
            PtPackage.cancelled_at.is_(None),
            Member.is_archived.is_(False),
            pt_owed > 0,
        )
    )
    pt_owing = db.execute(
        pt_owing_stmt.join(StaffUser, StaffUser.id == PtPackage.trainer_id)
        .add_columns(
            Member.name.label("member_name"),
            Member.phone,
            StaffUser.name.label("trainer_name"),
            pt_owed.label("owed"),
        )
        .order_by(pt_owed.desc(), Member.name)
        .limit(FOLLOW_UP_SHOWN)
    ).all()
    away_stmt = members_service.search(ctx, today=today, not_visiting_days=days)
    last_visit = members_service.last_visit_expression()
    away = list(
        db.scalars(
            away_stmt.order_by(last_visit.desc().nulls_last(), Member.name).limit(
                FOLLOW_UP_SHOWN
            )
        )
    )

    everyone = list({m.id: m for m in [*ending, *owing, *away]}.values())
    states = members_service.states_for(db, everyone, today)
    visits = members_service.last_visits(db, [m.id for m in everyone])

    def read(member: Member):
        item = member_read(member, states[member.id])
        item.last_visit_at = visits.get(member.id)
        return item

    def count(stmt) -> int:
        return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    lists = FollowUpLists(
        due_today=[],
        due_this_week=[],
        lapsed=[],
        owing=[read(m) for m in owing],
        owing_total=count(owing_stmt),
        pt_owing=[
            PtOwing(
                package_id=row.PtPackage.id,
                member_id=row.PtPackage.member_id,
                name=row.member_name,
                phone=row.phone,
                plan_name=row.PtPackage.plan_name,
                trainer_name=row.trainer_name,
                end_date=row.PtPackage.end_date,
                dues=row.owed,
            )
            for row in pt_owing
        ],
        pt_owing_total=count(pt_owing_stmt),
        not_visiting=[read(m) for m in away],
        not_visiting_total=count(away_stmt),
        not_visiting_days=days,
    )
    for member in sorted(ending, key=lambda m: (states[m.id].valid_until, m.name)):
        end = states[member.id].valid_until
        if end is None:
            continue
        if end == today:
            lists.due_today.append(read(member))
        elif today < end <= today + dt.timedelta(days=WEEK):
            lists.due_this_week.append(read(member))
        elif today - dt.timedelta(days=LAPSED_DAYS) <= end < today:
            lists.lapsed.append(read(member))
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


@router.get("/members/{member_id}/message", response_model=MemberMessage)
def member_message(
    member_id: uuid.UUID,
    purpose: MessagePurpose = "reminder",
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_VIEW)),
) -> MemberMessage:
    """The gym's own wording for this member, for WhatsApp from the desk's
    phone (§18.5). Free, sent by the person tapping Send: nothing goes from
    here, and no SMS credit is used. Anyone who can see the member and call
    them can message them."""
    member = load_member(db, ctx, member_id)
    members_service.ensure_not_erased(member)
    gym = _gym(db, ctx)
    return MemberMessage(
        text=reminders.message_text(db, gym, member, purpose), phone=member.phone
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
    """A one-off SMS, or "Send reminder now" from Follow up."""
    member = load_member(db, ctx, member_id)
    members_service.ensure_not_erased(member)
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


@router.post("/members/sms", response_model=BulkSmsResult)
def sms_members(
    payload: BulkSmsIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MESSAGES_SMS)),
) -> BulkSmsResult:
    """One message to the members picked on the Members list (§16.2, 7.6).

    Only this gym's members the sender may see; archived and erased ones are
    left out. One SMS each, queued together.
    """
    members = db.scalars(
        members_service.search(ctx).where(
            Member.id.in_(payload.member_ids), Member.erased_at.is_(None)
        )
    ).all()
    if len(members) != len(set(payload.member_ids)):
        raise not_found("Some of those members can't be found.")
    for member in members:
        sms.queue(
            db,
            gym_id=ctx.gym_id,
            to=member.phone,
            body=payload.body,
            kind=SMS_MANUAL,
            member_id=member.id,
            created_by=ctx.staff.id,
            flush=False,
        )
    db.flush()
    activity.staff_action(
        db,
        ctx.staff,
        "sms.sent_to_members",
        entity="member",
        changes={"members": len(members)},
        request=request,
    )
    db.commit()
    return BulkSmsResult(queued=len(members))


# --- reminder rules and wording -----------------------------------------------------

SETUP_REMINDERS = require(Permission.SETUP_REMINDERS)
RULE_TAKEN = AppError(
    409, "rule_exists", "There is already an automation for that day."
)


def _whatsapp_text(gym: Gym, key: str) -> str:
    """Our template as the gym's members would read it, {placeholders} kept."""
    language, _ = meta_language(gym.config.language)
    return TEMPLATES[key].text[language]


def rule_read(gym: Gym, rule: ReminderRule) -> ReminderRuleRead:
    read = ReminderRuleRead.model_validate(rule)
    template = for_rule(rule.trigger, rule.days)
    read.whatsapp = _whatsapp_text(gym, template.key) if template else None
    return read


@router.get("/reminder-rules", response_model=list[ReminderRuleRead])
def list_rules(
    db: Session = Depends(get_db), ctx: StaffContext = Depends(SETUP_REMINDERS)
) -> list[ReminderRuleRead]:
    gym = _gym(db, ctx)
    stmt = for_gym(select(ReminderRule), ReminderRule, ctx)
    return [
        rule_read(gym, rule)
        for rule in db.scalars(stmt.order_by(ReminderRule.trigger, ReminderRule.days))
    ]


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
) -> ReminderRuleRead:
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
    return rule_read(_gym(db, ctx), rule)


@router.patch("/reminder-rules/{rule_id}", response_model=ReminderRuleRead)
def update_rule(
    rule_id: uuid.UUID,
    payload: ReminderRuleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SETUP_REMINDERS),
) -> ReminderRuleRead:
    rule = get_in_gym(db, ReminderRule, rule_id, ctx, message="No such reminder.")
    fields = ("days", "template", "enabled")
    before = {f: getattr(rule, f) for f in fields}
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "days" in changes:
        try:
            check_days(rule.trigger, changes["days"])
        except ValueError as exc:
            raise AppError(422, "bad_days", str(exc)) from exc
    for name, value in changes.items():
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
    return rule_read(_gym(db, ctx), rule)


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
        changes={"trigger": rule.trigger, "days": rule.days, "template": rule.template},
        request=request,
    )
    db.delete(rule)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _templates(gym: Gym) -> SmsTemplates:
    config = gym.config
    return SmsTemplates(
        welcome_sms=config.welcome_sms,
        membership_sms=config.membership_sms,
        also_sms=config.also_sms,
        whatsapp=whatsapp.available() and config.whatsapp,
        welcome_whatsapp=_whatsapp_text(gym, "welcome"),
        membership_whatsapp=_whatsapp_text(gym, "membership_active"),
    )


@router.get("/sms-templates", response_model=SmsTemplates)
def get_templates(
    db: Session = Depends(get_db), ctx: StaffContext = Depends(SETUP_REMINDERS)
) -> SmsTemplates:
    return _templates(_gym(db, ctx))


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
    return _templates(gym)


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
    """What sending this notice would cost, before sending it (§7, §16.3 8.3):
    members whose phone takes push get it free (always sent); with SMS
    ticked, the rest by SMS."""
    gym = _gym(db, ctx)
    recipients = notice_recipients(db, ctx, payload.branch_id)
    by_push = len(push.reachable(db, [m.id for m in recipients]))
    by_sms = len(recipients) if gym.config.also_sms else len(recipients) - by_push
    each = segments(_notice_sms(gym, payload.title, payload.body))
    return NoticeCost(
        recipients=len(recipients),
        by_push=by_push,
        by_sms=by_sms,
        segments_each=each,
        total_credits=by_sms * each,
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
    if payload.send_sms and not ctx.can(Permission.MESSAGES_SMS):
        raise AppError(
            403,
            "permission_denied",
            "You don't have permission to do this.",
            permission=Permission.MESSAGES_SMS.value,
        )
    # Every notice goes by push to the members who turned notifications on:
    # it's free. SMS, which uses credits, only when asked for, and only to
    # the members push can't reach (or everyone, with the gym's "also SMS").
    text = _notice_sms(gym, payload.title, payload.body)
    recipients = notice_recipients(db, ctx, payload.branch_id)
    pushable = push.reachable(db, [m.id for m in recipients])
    for member in recipients:
        if not payload.send_sms and member.id not in pushable:
            continue
        channel, _ = push.notify(
            db,
            gym,
            member,
            title=payload.title,
            body=payload.body,
            url=f"/{gym.slug}/notices",
            tag=f"notice:{notice.id}",
            sms_body=text,
            sms_kind=SMS_NOTICE,
            created_by=ctx.staff.id,
            pushable=pushable,
            flush=False,
            sms_allowed=payload.send_sms,
        )
        notice.push_count += channel in ("push", "both")
        notice.sms_count += channel in ("sms", "both")
    db.flush()
    activity.staff_action(
        db,
        ctx.staff,
        "notice.published",
        entity="notice",
        entity_id=notice.id,
        changes={
            "title": notice.title,
            "sms_count": notice.sms_count,
            "push_count": notice.push_count,
        },
        request=request,
    )
    live.publish(db, gym_id=ctx.gym_id, kind=live.NOTICE, branch_id=notice.branch_id)
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
    live.publish(db, gym_id=ctx.gym_id, kind=live.NOTICE, branch_id=notice.branch_id)
    db.delete(notice)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
