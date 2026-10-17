"""The real Web Push provider: encrypted for the phone, signed with our key
(PLAN.md §16.3, 8.3). Nothing leaves the machine: the HTTP call is caught."""

import base64
import json
from types import SimpleNamespace

import http_ece
import jwt
import pytest
import pywebpush
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.core.push_keys import public_key
from app.services.push.providers import (
    PushError,
    PushGone,
    PushMessage,
    Target,
    WebPushProvider,
)


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@pytest.fixture
def phone():
    """A browser's subscription keys, as PushManager.subscribe() makes them."""
    key = ec.generate_private_key(ec.SECP256R1())
    point = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    auth = b"0123456789abcdef"
    target = Target(
        endpoint="https://fcm.googleapis.com/fcm/send/abc",
        p256dh=b64(point),
        auth=b64(auth),
    )
    return SimpleNamespace(key=key, auth=auth, target=target)


def catch(monkeypatch, status: int = 201) -> list[dict]:
    calls: list[dict] = []

    def post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return SimpleNamespace(
            status_code=status, reason="", text="", headers={}, content=b""
        )

    monkeypatch.setattr(pywebpush.requests, "post", post)
    return calls


def test_the_phone_can_read_it_and_it_is_ours(monkeypatch, phone) -> None:
    calls = catch(monkeypatch)
    message = PushMessage(
        title="Fitness Zone", body="3 days left", url="/fitness-zone/renew", tag="t"
    )
    WebPushProvider().send(phone.target, message)

    [call] = calls
    assert call["url"] == phone.target.endpoint
    headers = {k.lower(): v for k, v in call["headers"].items()}
    assert headers["content-encoding"] == "aes128gcm"
    assert int(headers["ttl"]) == 24 * 60 * 60
    # Only the phone's private key opens it.
    plain = http_ece.decrypt(
        call["data"], private_key=phone.key, auth_secret=phone.auth, version="aes128gcm"
    )
    assert json.loads(plain) == message.__dict__
    # Signed by our VAPID key, for this push service only.
    scheme, params = headers["authorization"].split(" ", 1)
    assert scheme == "vapid"
    fields = dict(p.strip().split("=", 1) for p in params.split(","))
    assert fields["k"] == public_key()
    point = unb64(fields["k"])
    verifier = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), point)
    claims = jwt.decode(
        fields["t"],
        verifier,
        algorithms=["ES256"],
        audience="https://fcm.googleapis.com",
    )
    assert claims["sub"] == "mailto:support@gymbhai.com"


@pytest.mark.parametrize("status", [404, 410])
def test_a_gone_subscription(monkeypatch, phone, status: int) -> None:
    catch(monkeypatch, status)
    with pytest.raises(PushGone):
        WebPushProvider().send(phone.target, PushMessage("t", "b", "/"))


def test_a_failing_push_service(monkeypatch, phone) -> None:
    catch(monkeypatch, 503)
    with pytest.raises(PushError) as caught:
        WebPushProvider().send(phone.target, PushMessage("t", "b", "/"))
    assert not isinstance(caught.value, PushGone)
