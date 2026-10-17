"""Authenticator codes (app/core/totp.py)."""

import datetime as dt
import uuid
from urllib.parse import parse_qs, urlparse

from app.core import totp

# RFC 6238 Appendix B, SHA-1: the ASCII secret "12345678901234567890". The RFC
# lists 8-digit codes; ours are their last 6 digits.
RFC_SECRET = b"12345678901234567890"
RFC_VECTORS = {
    59: "287082",
    1111111109: "081804",
    1111111111: "050471",
    1234567890: "005924",
    2000000000: "279037",
}


def at(seconds: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(seconds, tz=dt.UTC)


def test_the_rfc_test_vectors() -> None:
    for seconds, code in RFC_VECTORS.items():
        assert totp.code_at(RFC_SECRET, totp.step_at(at(seconds))) == code


def test_a_code_from_the_step_before_or_after_still_works() -> None:
    now = at(1_000_000_000)
    step = totp.step_at(now)
    for drift in (-1, 0, 1):
        code = totp.code_at(RFC_SECRET, step + drift)
        assert totp.verify(RFC_SECRET, code, after_step=None, now=now) == step + drift
    two_away = totp.code_at(RFC_SECRET, step + 2)
    assert totp.verify(RFC_SECRET, two_away, after_step=None, now=now) is None


def test_a_used_code_is_refused() -> None:
    now = at(1_000_000_000)
    step = totp.step_at(now)
    code = totp.code_at(RFC_SECRET, step)
    assert totp.verify(RFC_SECRET, code, after_step=step, now=now) is None
    assert totp.verify(RFC_SECRET, code, after_step=step - 1, now=now) == step


def test_spaces_in_a_typed_code_are_ignored() -> None:
    now = at(1_000_000_000)
    code = totp.code_at(RFC_SECRET, totp.step_at(now))
    spaced = f"{code[:3]} {code[3:]}"
    assert totp.verify(RFC_SECRET, spaced, after_step=None, now=now) is not None
    assert totp.verify(RFC_SECRET, "12345", after_step=None, now=now) is None


def test_each_account_and_nonce_has_its_own_secret() -> None:
    account = uuid.uuid4()
    first = totp.secret_for(account, "a")
    assert len(first) == 20
    assert first == totp.secret_for(account, "a")
    assert first != totp.secret_for(account, "b")
    assert first != totp.secret_for(uuid.uuid4(), "a")


def test_the_setup_link() -> None:
    uri = urlparse(totp.provisioning_uri(RFC_SECRET, "sita@example.com"))
    assert uri.scheme == "otpauth"
    assert uri.netloc == "totp"
    assert uri.path == "/GymBhai%3Asita%40example.com"
    query = parse_qs(uri.query)
    assert query["secret"] == ["GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"]
    assert query["issuer"] == ["GymBhai"]
    assert query["digits"] == ["6"]
    assert query["period"] == ["30"]
