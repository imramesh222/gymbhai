"""ZKTeco and eSSL readers over ADMS, their "cloud server" protocol (PLAN.md
§18.2): the reader calls us, so a gym needs nothing but the reader and its
internet.

    GET  /iclock/cdata?SN=                 starting up: what to send, how often
    POST /iclock/cdata?SN=&table=ATTLOG    scans
    POST /iclock/cdata?SN=&table=OPERLOG   its own log: read for nothing, and any
                                           fingerprint template in it dropped
    GET  /iclock/getrequest?SN=            the changes waiting for it
    POST /iclock/devicecmd?SN=             how each went

Plain text both ways, as the readers speak it. A reader is known by its serial
number, entered when the gym added it in Settings → Door scanners; any other
serial is refused. Built to ZKTeco's published push protocol; to be confirmed
on a real reader before a gym relies on it (§18.2).
"""

from typing import Annotated
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.time import utcnow
from app.db.session import get_db
from app.models.gym import GYM_ACTIVE, Gym
from app.models.member_app import DEVICE_ZKTECO, Device
from app.services import readers

router = APIRouter(prefix="/iclock", tags=["readers"])

Serial = Annotated[str, Query(alias="SN", min_length=1, max_length=64)]

# What the reader is told when it starts. Scans as they happen (Realtime) and
# its operation log; no photos, no fingerprint templates asked for.
OPTIONS = (
    "ATTLOGStamp=None",
    "OPERLOGStamp=9999",
    "ATTPHOTOStamp=None",
    "ErrorDelay=30",
    "Delay=10",
    "TransTimes=00:00;14:05",
    "TransInterval=1",
    "TransFlag=TransData AttLog\tOpLog",
    "Realtime=1",
    "Encrypt=None",
)


def text(body: str) -> PlainTextResponse:
    return PlainTextResponse(body)


async def raw_body(request: Request) -> str:
    """What the reader sent: lines of text, whatever it says the type is."""
    return (await request.body()).decode("utf-8", errors="replace")


def _reader(db: Session, serial: str) -> Device:
    device = db.scalar(
        select(Device).where(
            Device.serial == serial,
            Device.kind == DEVICE_ZKTECO,
            Device.revoked_at.is_(None),
        )
    )
    gym = db.get(Gym, device.gym_id) if device is not None else None
    if device is None or gym is None or gym.status != GYM_ACTIVE:
        raise AppError(404, "unknown_reader", "This reader isn't registered.")
    device.last_seen_at = utcnow()
    return device


@router.get("/cdata", response_class=PlainTextResponse)
def start(serial: Serial, db: Session = Depends(get_db)) -> PlainTextResponse:
    _reader(db, serial)
    db.commit()
    return text("\n".join([f"GET OPTION FROM: {serial}", *OPTIONS]) + "\n")


@router.post("/cdata", response_class=PlainTextResponse)
def upload(
    serial: Serial,
    table: Annotated[str, Query(max_length=32)] = "",
    body: str = Depends(raw_body),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    """Scans become check-ins; everything else is acknowledged and dropped,
    fingerprint templates above all: they stay on the reader."""
    device = _reader(db, serial)
    lines = [line for line in body.splitlines() if line.strip()]
    if table.upper() == "ATTLOG":
        for line in lines:
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            try:
                at = readers.local_time(parts[1])
                verify = int(parts[3]) if len(parts) > 3 and parts[3].strip() else 1
            except ValueError:
                continue
            readers.scan(
                db,
                device,
                parts[0],
                at,
                readers.ZKTECO_VERIFY.get(verify, readers.METHOD_FINGERPRINT),
            )
    db.commit()
    return text(f"OK: {len(lines)}")


@router.get("/getrequest", response_class=PlainTextResponse)
def waiting(serial: Serial, db: Session = Depends(get_db)) -> PlainTextResponse:
    """The changes for this reader, one a line, or OK for none."""
    device = _reader(db, serial)
    lines = [_line(command) for command in readers.commands(db, device)]
    db.commit()
    return text("\n".join(lines) + "\n" if lines else "OK")


def _clean(value: str) -> str:
    return " ".join(value.replace("\t", " ").split())


def _line(command: readers.Command) -> str:
    if command.action == "remove":
        return f"C:{command.id}:DATA DELETE USERINFO PIN={command.pin}"
    fields = [
        f"PIN={command.pin}",
        f"Name={_clean(command.name)}",
        "Pri=0",
        "Passwd=",
        "Card=",
        "Grp=1",
        "TZ=0000000100000000",
        "Verify=0",
    ]
    return f"C:{command.id}:DATA UPDATE USERINFO " + "\t".join(fields)


@router.post("/devicecmd", response_class=PlainTextResponse)
def done(
    serial: Serial,
    body: str = Depends(raw_body),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    """ "ID=12&Return=0&CMD=DATA", a line for each: 0 is done."""
    device = _reader(db, serial)
    for line in body.splitlines():
        fields = parse_qs(line.strip())
        try:
            command_id = int(fields["ID"][0])
            code = int(fields.get("Return", ["0"])[0])
        except (KeyError, ValueError):
            continue
        readers.answered(
            db, device, command_id, code >= 0, None if code >= 0 else f"Return={code}"
        )
    db.commit()
    return text("OK")
