"""What's new in GymBhai (PLAN.md §16.5, 10.4): entries we write in /admin; a
dot for each staff member until they've opened the newest."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.platform import ChangelogEntry
from app.models.staff import StaffUser

SHOWN = 20


def published(db: Session) -> list[ChangelogEntry]:
    return list(
        db.scalars(
            select(ChangelogEntry)
            .where(
                ChangelogEntry.published_at.is_not(None),
                ChangelogEntry.published_at <= utcnow(),
            )
            .order_by(ChangelogEntry.published_at.desc())
            .limit(SHOWN)
        )
    )


def unread(db: Session, staff: StaffUser) -> bool:
    newest = db.scalar(
        select(func.max(ChangelogEntry.published_at)).where(
            ChangelogEntry.published_at <= utcnow()
        )
    )
    if newest is None:
        return False
    return staff.changelog_seen_at is None or staff.changelog_seen_at < newest


def seen(staff: StaffUser) -> None:
    staff.changelog_seen_at = utcnow()
