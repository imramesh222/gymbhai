import pytest
from pydantic import ValidationError

from app.core.gym_settings import GymSettings
from app.schemas.auth import GymSignup

SIGNUP = dict(
    gym_name="Fitness Zone",
    slug="fitness-zone",
    owner_name="Sita Sharma",
    owner_phone="9841234567",
    password="correct-horse-battery",
)


def test_calendar_has_no_default() -> None:
    with pytest.raises(ValidationError):
        GymSettings()  # type: ignore[call-arg]


def test_sign_up_requires_both_calendar_choices() -> None:
    with pytest.raises(ValidationError) as err:
        GymSignup(**SIGNUP)  # type: ignore[arg-type]
    missing = {e["loc"][0] for e in err.value.errors()}
    assert {"plan_months", "date_display"} <= missing


def test_sign_up_with_calendar_choices() -> None:
    signup = GymSignup(**SIGNUP, plan_months="bs", date_display="both")
    assert signup.plan_months == "bs"


def test_sign_up_needs_a_phone_or_an_email() -> None:
    with pytest.raises(ValidationError):
        GymSignup(**{**SIGNUP, "owner_phone": ""}, plan_months="ad", date_display="ad")


def test_sign_up_refuses_a_gym_id_in_the_body() -> None:
    with pytest.raises(ValidationError):
        GymSignup(**SIGNUP, plan_months="ad", date_display="ad", gym_id="anything")  # type: ignore[call-arg]
