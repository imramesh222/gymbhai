"""What's new in GymBhai, for staff (PLAN.md §16.5, 10.4)."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.tenancy import StaffContext
from app.db.session import get_db
from app.schemas.platform import ChangelogRead
from app.services import changelog

router = APIRouter(prefix="/changelog", tags=["what's new"])


@router.get("", response_model=list[ChangelogRead])
def whats_new(
    db: Session = Depends(get_db), ctx: StaffContext = Depends(require())
) -> list[ChangelogRead]:
    return [ChangelogRead.model_validate(e) for e in changelog.published(db)]


@router.post("/seen", status_code=status.HTTP_204_NO_CONTENT)
def mark_seen(
    db: Session = Depends(get_db), ctx: StaffContext = Depends(require())
) -> Response:
    """Opened What's new: the dot goes until the next entry."""
    staff = db.merge(ctx.staff)
    changelog.seen(staff)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
