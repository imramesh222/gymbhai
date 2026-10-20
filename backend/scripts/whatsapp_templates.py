"""Our WhatsApp templates, as Meta's template API takes them (PLAN.md §19.3).

    docker compose exec api python -m scripts.whatsapp_templates
    docker compose exec api python -m scripts.whatsapp_templates --create \
        --waba 123456789012345
    docker compose exec api python -m scripts.whatsapp_templates --send-test \
        98XXXXXXXX --template membership_ends

With no option it prints each template in each language as the JSON for
POST /<WhatsApp Business Account id>/message_templates, to read or paste.
--create submits them for review with WHATSAPP_TOKEN (a template already
there is reported, not changed). --send-test sends one to a number, which
Meta charges for; the number must have agreed to hear from us.

Meta numbers the variables {{1}}, {{2}}… and wants an example of each. The
button's link starts at PUBLIC_APP_URL: set it to the real address first.
"""

import argparse
import json
import sys

import httpx

from app.core.config import settings
from app.core.whatsapp_templates import LANGUAGES, TEMPLATES, Template, meta_language
from app.services.whatsapp.providers import (
    GRAPH,
    Outgoing,
    WhatsAppError,
    get_provider,
)

# What Meta's reviewers see in place of each variable.
EXAMPLES = {
    "name": "Sita",
    "gym": "Himalayan Fitness Club",
    "plan": "3 months",
    "end_date": "15 Kartik 2083",
    "from_date": "1 Kartik 2083",
    "to_date": "10 Kartik 2083",
    "amount": "1,500",
    "trainer": "Bikash",
    "reason": "amount not received",
    "receipt": "142",
}
BUTTON_EXAMPLES = {"app": "himalayan-fitness/renew", "receipt": "abc.pdf"}


def payload(template: Template, language: str) -> dict:
    _, code = meta_language(language)
    order = template.variables(language)
    components: list[dict] = [
        {
            "type": "BODY",
            "text": template.meta_body(language),
            **(
                {"example": {"body_text": [[EXAMPLES[name] for name in order]]}}
                if order
                else {}
            ),
        }
    ]
    if template.button:
        components.append(
            {
                "type": "BUTTONS",
                "buttons": [
                    {
                        "type": "URL",
                        "text": template.button.label[language],
                        "url": template.button.url() + "{{1}}",
                        "example": [
                            template.button.url()
                            + BUTTON_EXAMPLES[template.button.base]
                        ],
                    }
                ],
            }
        )
    return {
        "name": template.name,
        "language": code,
        "category": template.category,
        "components": components,
    }


def all_payloads() -> list[dict]:
    seen = set()
    rows = []
    for template in TEMPLATES.values():
        for language in LANGUAGES:
            row = payload(template, language)
            if (row["name"], row["language"]) in seen:
                continue  # Nepali sent as English: one copy
            seen.add((row["name"], row["language"]))
            rows.append(row)
    return rows


def create(waba: str) -> int:
    if not settings.whatsapp_token:
        print("WHATSAPP_TOKEN is not set.", file=sys.stderr)
        return 1
    url = f"{GRAPH}/{settings.whatsapp_api_version}/{waba}/message_templates"
    failed = 0
    with httpx.Client(timeout=30) as client:
        for row in all_payloads():
            response = client.post(
                url,
                json=row,
                headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
            )
            data = response.json()
            name = f"{row['name']} ({row['language']})"
            if response.status_code == 200:
                print(f"submitted {name}: {data.get('status')}")
            else:
                failed += 1
                error = data.get("error") or {}
                print(f"refused {name}: {error.get('message')}", file=sys.stderr)
    return 1 if failed else 0


def send_test(to: str, key: str) -> int:
    template = TEMPLATES[key]
    language, code = meta_language("en")
    button = None
    if template.button:
        button = BUTTON_EXAMPLES[template.button.base]
    message = Outgoing(
        to=to,
        template=template.name,
        language=code,
        values=template.values(language, EXAMPLES),
        button=button,
    )
    provider = get_provider()
    print(f"WHATSAPP_PROVIDER={settings.whatsapp_provider} -> {provider.name}")
    try:
        sent = provider.send_template(message)
    except WhatsAppError as exc:
        print(f"not sent: {exc}", file=sys.stderr)
        return 1
    print(f"sent: {sent.provider_ref}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--create", action="store_true", help="submit them to Meta")
    parser.add_argument("--waba", help="the WhatsApp Business Account id")
    parser.add_argument("--send-test", metavar="PHONE", help="send one to 98XXXXXXXX")
    parser.add_argument("--template", default="membership_ends", choices=TEMPLATES)
    args = parser.parse_args()
    if args.send_test:
        return send_test(args.send_test, args.template)
    if args.create:
        if not args.waba:
            print("--create needs --waba", file=sys.stderr)
            return 2
        return create(args.waba)
    print(json.dumps(all_payloads(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
