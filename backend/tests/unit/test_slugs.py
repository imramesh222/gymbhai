import pytest

from app.core.slugs import RESERVED_SLUGS, check_slug


@pytest.mark.parametrize("slug", ["fitness-zone", "gym42", "abc", "a" * 40])
def test_good_slugs(slug: str) -> None:
    assert check_slug(slug) == slug


def test_slugs_are_lower_cased() -> None:
    assert check_slug(" Fitness-Zone ") == "fitness-zone"


@pytest.mark.parametrize(
    "slug", ["ab", "a" * 41, "-gym", "gym-", "fit--zone", "fit zone", "fit_zone"]
)
def test_bad_shapes(slug: str) -> None:
    with pytest.raises(ValueError):
        check_slug(slug)


@pytest.mark.parametrize("slug", ["staff", "kiosk", "admin", "api", "signup"])
def test_our_own_routes_cannot_be_taken(slug: str) -> None:
    assert slug in RESERVED_SLUGS
    with pytest.raises(ValueError, match="reserved"):
        check_slug(slug)
