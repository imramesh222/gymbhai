import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.auth import MIN_PASSWORD_LENGTH, OptionalEmail, OptionalPhone, Strict


class StaffMember(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    is_owner: bool
    is_active: bool
    permissions: list[str]
    # Empty means every branch.
    branch_ids: list[uuid.UUID] = []
    last_login_at: dt.datetime | None
    created_at: dt.datetime


class StaffCreate(Strict):
    name: str = Field(min_length=2, max_length=120)
    email: OptionalEmail = None
    phone: OptionalPhone = None
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=72)
    permissions: list[str] = []
    branch_ids: list[uuid.UUID] = []

    @model_validator(mode="after")
    def has_login(self) -> "StaffCreate":
        if not self.email and not self.phone:
            raise ValueError("Give a phone number or an email to sign in with.")
        return self


class StaffUpdate(Strict):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    email: OptionalEmail = None
    phone: OptionalPhone = None
    permissions: list[str] | None = None
    branch_ids: list[uuid.UUID] | None = None
    is_active: bool | None = None


class PasswordSet(Strict):
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=72)


class PasswordChange(Strict):
    """Your own password. The current one is required even though you are
    signed in: a token lifted from a desk PC must not be enough to lock the
    real person out."""

    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=72)


class PermissionInfo(BaseModel):
    key: str
    area: str


class PermissionCatalog(BaseModel):
    permissions: list[PermissionInfo]
    presets: dict[str, list[str]]
    # What the caller may hand out.
    grantable: list[str]
