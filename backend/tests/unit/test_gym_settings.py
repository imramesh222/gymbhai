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
    accept_terms=True,
)


def test_plan_months_start_unchosen_and_dates_show_both() -> None:
    config = GymSettings()
    assert config.plan_months is None
    assert config.date_display == "both"


def test_sign_up_asks_nothing_about_the_calendar() -> None:
    GymSignup(**SIGNUP)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        GymSignup(**SIGNUP, plan_months="bs")  # type: ignore[call-arg]


def test_sign_up_needs_a_phone_or_an_email() -> None:
    with pytest.raises(ValidationError):
        GymSignup(**{**SIGNUP, "owner_phone": ""})  # type: ignore[arg-type]


def test_sign_up_refuses_a_gym_id_in_the_body() -> None:
    with pytest.raises(ValidationError):
        GymSignup(**SIGNUP, gym_id="anything")  # type: ignore[call-arg]
