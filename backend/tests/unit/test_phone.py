import pytest

from app.core.phone import normalize_phone


@pytest.mark.parametrize(
    "raw",
    [
        "9841234567",
        "984-1234567",
        "984 123 4567",
        "+977 9841234567",
        "+977-984-1234567",
        "009779841234567",
        "9779841234567",
    ],
)
def test_common_ways_of_writing_one_number_are_one_number(raw: str) -> None:
    assert normalize_phone(raw) == "9841234567"


def test_97_prefix_is_a_mobile_number() -> None:
    assert normalize_phone("9741234567") == "9741234567"


@pytest.mark.parametrize(
    "raw",
    [
        "014412345",  # Kathmandu landline
        "984123456",  # one digit short
        "98412345678",  # one digit long
        "9641234567",  # not 98/97
        "abcdefghij",
        "",
        "+977 01 4412345",
    ],
)
def test_anything_else_is_refused(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_phone(raw)
