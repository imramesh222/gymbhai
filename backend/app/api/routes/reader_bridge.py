"""The bridge at a gym with a Hikvision reader (PLAN.md §18.2).

GymBhai can't reach a reader on the gym's own network, so a small program
there (`bridge/hikvision_bridge.py`, on a PC or a Raspberry Pi) does it: it
collects the changes for its reader from here and makes them over the
reader's ISAPI, and passes on the scans it reads from the reader's log. It
signs in with the reader's device token, as a kiosk does, and can do nothing
else.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_device
from app.core.errors import AppError
from app.db.session import get_db
from app.models.member_app import DEVICE_HIKVISION, Device
from app.schemas.readers import (
    ReaderCommand,
    ReaderCommands,
    ReaderEvents,
    ReaderReport,
    ReaderResults,
)
from app.services import readers

router = APIRouter(prefix="/kiosk/reader", tags=["readers"])


def bridged_reader(device: Device = Depends(current_device)) -> Device:
    if device.kind != DEVICE_HIKVISION:
        raise AppError(
            409, "not_a_bridged_reader", "This device isn't a reader with a bridge."
        )
    return device


@router.get("/commands", response_model=ReaderCommands)
def commands(
    db: Session = Depends(get_db), device: Device = Depends(bridged_reader)
) -> ReaderCommands:
    """The changes for the reader, oldest first; sent again until answered."""
    found = readers.commands(db, device)
    db.commit()
    return ReaderCommands(
        commands=[
            ReaderCommand(
                id=c.id, action=c.action, pin=c.pin, name=c.name, until=c.until
            )
            for c in found
        ]
    )


@router.post("/results", response_model=ReaderReport)
def results(
    payload: ReaderResults,
    db: Session = Depends(get_db),
    device: Device = Depends(bridged_reader),
) -> ReaderReport:
    answered = sum(
        readers.answered(db, device, r.id, r.ok, r.error) for r in payload.results
    )
    db.commit()
    return ReaderReport(answered=answered)


@router.post("/events", response_model=ReaderReport)
def events(
    payload: ReaderEvents,
    db: Session = Depends(get_db),
    device: Device = Depends(bridged_reader),
) -> ReaderReport:
    """Scans, as check-ins under the same rules as a QR scan. Sent twice, a
    scan is recorded once."""
    recorded = sum(
        readers.scan(db, device, e.pin, e.at, e.how) is not None for e in payload.events
    )
    db.commit()
    return ReaderReport(recorded=recorded)
