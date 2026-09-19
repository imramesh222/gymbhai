import datetime as dt
import uuid

import jwt
import pytest

from app.core import security
from app.core.config import settings


def test_password_round_trip() -> None:
    hashed = security.hash_password("correct-horse-battery")
    assert security.verify_password("correct-horse-battery", hashed)
    assert not security.verify_password("wrong", hashed)


def test_over_long_passwords_are_refused_not_truncated() -> None:
    with pytest.raises(ValueError):
        security.hash_password("x" * 73)
    assert not security.verify_password("x" * 73, security.hash_password("x" * 72))


def test_a_malformed_hash_is_a_wrong_password() -> None:
    assert not security.verify_password("anything", "not-a-bcrypt-hash")


def test_access_token_round_trip() -> None:
    ids = dict(staff_id=uuid.uuid4(), gym_id=uuid.uuid4(), session_id=uuid.uuid4())
    claims = security.decode_access_token(security.create_access_token(**ids))
    assert (claims.staff_id, claims.gym_id, claims.session_id) == tuple(ids.values())


def test_platform_admin_token_has_no_gym() -> None:
    token = security.create_access_token(
        staff_id=uuid.uuid4(), gym_id=None, session_id=uuid.uuid4()
    )
    assert security.decode_access_token(token).gym_id is None


def _signed(payload: dict) -> str:
    return jwt.encode(payload, settings.secret_key, algorithm=security.ALGORITHM)


def test_expired_token() -> None:
    past = int((dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)).timestamp())
    token = _signed({"typ": "access", "sub": str(uuid.uuid4()), "exp": past})
    with pytest.raises(security.TokenError) as err:
        security.decode_access_token(token)
    assert err.value.code == "session_expired"


def test_token_of_another_type_is_refused() -> None:
    token = _signed({"typ": "something-else", "sub": str(uuid.uuid4())})
    with pytest.raises(security.TokenError):
        security.decode_access_token(token)


def test_token_signed_with_another_key_is_refused() -> None:
    token = jwt.encode({"typ": "access"}, "another-key-" * 4, algorithm="HS256")
    with pytest.raises(security.TokenError):
        security.decode_access_token(token)


def test_refresh_tokens_are_random_and_stored_hashed() -> None:
    first, second = security.new_refresh_token(), security.new_refresh_token()
    assert first != second
    assert security.hash_refresh_token(first) != first
    assert len(security.hash_refresh_token(first)) == 64


def test_a_fixed_sign_in_code_is_refused_outside_local_and_test() -> None:
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError, match="OTP_TEST_CODE"):
        Settings(
            environment="production",
            secret_key="x" * 40,
            otp_test_code="123456",
            _env_file=None,
        )
    assert Settings(environment="local", otp_test_code="123456", _env_file=None)
