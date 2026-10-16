"""The staff dashboard's live updates (app/services/live.py)."""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.tenancy import StaffContext
from app.core.config import settings
from app.db.session import get_db
from app.services import live

router = APIRouter(tags=["live"])


@router.get("/live")
def staff_live(
    db: Session = Depends(get_db), ctx: StaffContext = Depends(require())
) -> StreamingResponse:
    """Something changed that a screen may be showing. Every staff member may
    listen; each event is filtered by their permissions and branches."""
    accepts = live.staff_filter(ctx)
    # Not held for the life of the stream: one pooled connection per open
    # dashboard would soon use them all up.
    db.close()
    return StreamingResponse(
        live.stream(accepts, seconds=settings.access_token_minutes * 60),
        media_type="text/event-stream",
        headers=live.STREAM_HEADERS,
    )
