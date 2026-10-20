"""Fingerprint and face readers (PLAN.md §18.2)."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.schemas.auth import Strict

How = Literal["fingerprint", "face", "card", "pin"]


class ReaderIn(Strict):
    """Settings → Door scanners → Add a fingerprint or face reader."""

    kind: Literal["zkteco", "hikvision"]
    name: str = Field(min_length=1, max_length=80)
    branch_id: uuid.UUID
    # Menu → System Info on the reader. A ZKTeco reader says who it is with it.
    serial: str | None = Field(
        default=None, min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"
    )

    @model_validator(mode="after")
    def zkteco_needs_serial(self) -> "ReaderIn":
        if self.kind == "zkteco" and not self.serial:
            raise ValueError("A ZKTeco reader is known by its serial number.")
        return self


class ReaderCommand(BaseModel):
    """A change for the reader: put a member on it, or take them off."""

    id: int
    action: Literal["set", "remove"]
    pin: str
    name: str
    # The last day it should let them in; none: not now.
    until: dt.date | None


class ReaderCommands(BaseModel):
    commands: list[ReaderCommand]


class ReaderResult(Strict):
    id: int
    ok: bool
    error: str | None = Field(default=None, max_length=500)


class ReaderResults(Strict):
    results: list[ReaderResult] = Field(max_length=200)


class ReaderEvent(Strict):
    """A scan at the reader, as the bridge read it from the reader's log."""

    pin: str = Field(min_length=1, max_length=24)
    # With its offset: the reader's own clock, in Nepal time.
    at: AwareDatetime
    how: How = "face"


class ReaderEvents(Strict):
    events: list[ReaderEvent] = Field(max_length=500)


class ReaderReport(BaseModel):
    answered: int = 0
    recorded: int = 0
