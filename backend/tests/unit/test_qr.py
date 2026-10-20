import secrets
import uuid

from app.core import qr

SECRET = secrets.token_hex(32)
MEMBER = uuid.UUID("12345678-1234-5678-1234-567812345678")
NOW = 1_790_000_000.0


def code_at(unix: float, version: int = 1) -> str:
    return qr.app_code(MEMBER, qr.app_key(SECRET, version), qr.window_at(unix))


def test_a_fresh_code_verifies() -> None:
    scanned = qr.parse(code_at(NOW))
    assert scanned is not None and scanned.member_id == MEMBER
    assert qr.verify_app_code(scanned, SECRET, 1, now=NOW)


def test_one_window_of_clock_drift_either_side() -> None:
    for offset in (-30, 30):
        assert qr.verify_app_code(qr.parse(code_at(NOW + offset)), SECRET, 1, now=NOW)


def test_a_screenshot_stops_working_within_a_minute() -> None:
    old = qr.parse(code_at(NOW - 90))
    assert not qr.verify_app_code(old, SECRET, 1, now=NOW)


def test_bumping_the_version_revokes_the_phone() -> None:
    assert not qr.verify_app_code(qr.parse(code_at(NOW, version=1)), SECRET, 2, now=NOW)


def test_a_forged_signature_fails() -> None:
    code = code_at(NOW)
    forged = code[:-1] + ("A" if code[-1] != "A" else "B")
    assert not qr.verify_app_code(qr.parse(forged), SECRET, 1, now=NOW)


def test_another_members_key_does_not_work() -> None:
    other = qr.app_key(secrets.token_hex(32), 1)
    code = qr.app_code(MEMBER, other, qr.window_at(NOW))
    assert not qr.verify_app_code(qr.parse(code), SECRET, 1, now=NOW)


def test_cards_and_junk() -> None:
    card = qr.parse(qr.card_code("abcDEF123456"))
    assert (
        card is not None and card.kind == "card" and card.card_token == "abcDEF123456"
    )
    for junk in ("", "hello", "gb1.x.y.z", "gb2.a.b.c", "gbc.", "https://example.com"):
        assert qr.parse(junk) is None


def test_known_vector_for_the_frontend() -> None:
    """frontend/src/lib/memberQr.test.ts checks the same numbers."""
    key = qr.app_key("00" * 32, 1)
    assert key == "P-5VXu9nLNLOU1OTAEFX9jwIldfaTzZeyqhp38H3WLg"
    assert qr.app_code(MEMBER, key, 59_666_666) == (
        "gb1.12345678123456781234567812345678.59666666.uD4CqX4EAlGpxzdJ"
    )


# --- gb2: Ed25519, checkable offline (PLAN.md §19.2) -------------------------------


def code2_at(unix: float, version: int = 1) -> str:
    return qr.app_code2(MEMBER, qr.signing_key(SECRET, version), qr.window_at(unix))


def test_a_gb2_code_verifies_and_drifts_like_gb1() -> None:
    scanned = qr.parse(code2_at(NOW))
    assert scanned is not None and scanned.kind == "app2"
    assert qr.verify_app_code2(scanned, SECRET, 1, now=NOW)
    for offset in (-30, 30):
        assert qr.verify_app_code2(qr.parse(code2_at(NOW + offset)), SECRET, 1, now=NOW)
    assert not qr.verify_app_code2(qr.parse(code2_at(NOW - 90)), SECRET, 1, now=NOW)


def test_a_gb2_code_is_revoked_and_unforgeable() -> None:
    assert not qr.verify_app_code2(qr.parse(code2_at(NOW, 1)), SECRET, 2, now=NOW)
    code = code2_at(NOW)
    forged = code[:-2] + ("AA" if code[-2:] != "AA" else "BB")
    assert not qr.verify_app_code2(qr.parse(forged), SECRET, 1, now=NOW)
    # A gb1 signature under a gb2 label is still a bad signature.
    gb1 = code_at(NOW).replace("gb1.", "gb2.")
    assert not qr.verify_app_code2(qr.parse(gb1), SECRET, 1, now=NOW)


def test_known_gb2_vector_for_the_apps() -> None:
    """frontend/src/lib/hmac.test.ts signs and checks the same numbers."""
    key = qr.signing_key("00" * 32, 1)
    assert key == "mtbJK1LD-vbZuDVIEk8nqscuQojfRzEG9KZys-cjASc"
    assert qr.public_key("00" * 32, 1) == "p6tHitkllt09ERnscZwAyjqc2nL8DGBHkUO5H1VwTfQ"
    assert qr.app_code2(MEMBER, key, 59_666_666) == (
        "gb2.12345678123456781234567812345678.59666666."
        "na-qDqQPKYTID_k4B7bDXQjSYeixck8XrS4Ig5B5D6eydcFyeyP8B3SX6BHZDMAsXtSKkWCrVtbG4HbpV4YYAw"
    )
