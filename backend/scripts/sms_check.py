"""Check the SMS gateway with the settings this container is running with.

    docker compose exec api python -m scripts.sms_check
    docker compose exec api python -m scripts.sms_check --to 98XXXXXXXX

With no --to it only reads the account: enough to prove the token, the sender
and (on a server) that our address is whitelisted. With --to it sends one real
message, which costs a credit. Nothing here touches a gym's credit balance;
it talks to the gateway directly.
"""

import argparse
import sys

from app.core.config import settings
from app.core.phone import normalize_phone
from app.core.sms_text import segments
from app.services.sms.providers import SmsError, SparrowProvider, get_provider


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--to", help="a Nepali mobile number, e.g. 98XXXXXXXX")
    parser.add_argument("--text", default="GymBhai test message. Ignore.")
    args = parser.parse_args()

    provider = get_provider()
    print(f"SMS_PROVIDER={settings.sms_provider} -> {provider.name}")
    if isinstance(provider, SparrowProvider):
        print(f"sender: {settings.sparrow_sender}")
        try:
            print(f"credits available: {provider.credits()}")
        except SmsError as exc:
            print(f"credit check failed: {exc}", file=sys.stderr)
            return 1

    if not args.to:
        print("No --to, so nothing was sent.")
        return 0

    to = normalize_phone(args.to)
    print(f"sending {segments(args.text)} segment(s) to {to} ...")
    try:
        sent = provider.send(to, args.text)
    except SmsError as exc:
        print(f"send failed: {exc}", file=sys.stderr)
        return 1
    print(f"accepted by the gateway (ref: {sent.provider_ref or 'none given'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
