"""The WhatsApp messages GymBhai may send, as Meta has to approve them (PLAN.md
§19.3).

WhatsApp only delivers a business's first message as a template Meta approved,
so a gym's own SMS wording can't be used: each message here is ours, in
English and Nepali, with the gym's details filled in. Each is in Meta's
**utility** category (an update about the member's own membership, money or
request), which costs about a tenth of a marketing message; win-back,
birthday, not-visiting and notices are marketing, and stay push then SMS.

Wording is written with our `{placeholders}`; Meta is sent `{{1}}`, `{{2}}`…
in the order they appear in each language. Meta's rules, which
tests/unit/test_whatsapp_templates.py checks: no placeholder at the very start
or end of the body, never two side by side, and every value one line of text.
A template's wording, once approved, changes only under a new name: Meta
reviews it again.

`python -m scripts.whatsapp_templates` prints them as Meta's template API
takes them (docs/WHATSAPP.md).
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from app.core.config import settings

PREFIX = "gymbhai_"
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
# Meta refuses a parameter with a line break, a tab, or four spaces in a row.
_SPACE = re.compile(r"\s+")
MAX_VALUE = 200


@dataclass(frozen=True)
class Button:
    """One "open" button whose link ends with a value: the only place Meta
    lets a link vary. `base` is where the link starts."""

    label: dict[str, str]
    base: Literal["app", "receipt"] = "app"

    def url(self) -> str:
        root = settings.public_app_url.rstrip("/")
        if self.base == "receipt":
            return f"{root}{settings.api_v1_prefix}/receipts/"
        return f"{root}/"


OPEN_APP = Button({"en": "Open the app", "ne": "एप खोल्नुहोस्"})


@dataclass(frozen=True)
class Template:
    key: str
    text: dict[str, str]
    button: Button | None = OPEN_APP
    category: str = field(default="UTILITY")

    @property
    def name(self) -> str:
        """As registered with Meta."""
        return f"{PREFIX}{self.key}"

    def variables(self, language: str = "en") -> list[str]:
        """Our placeholders in the order Meta numbers them, for that language."""
        seen: list[str] = []
        for name in _PLACEHOLDER.findall(self.text[language]):
            if name not in seen:
                seen.append(name)
        return seen

    def meta_body(self, language: str) -> str:
        order = self.variables(language)
        return _PLACEHOLDER.sub(
            lambda m: "{{" + str(order.index(m.group(1)) + 1) + "}}",
            self.text[language],
        )

    def values(self, language: str, values: Mapping[str, object]) -> list[str]:
        return [clean(values.get(name)) for name in self.variables(language)]

    def render(self, language: str, values: Mapping[str, object]) -> str:
        """What the member reads, for the message log."""
        filled = dict(
            zip(self.variables(language), self.values(language, values), strict=True)
        )
        return _PLACEHOLDER.sub(lambda m: filled[m.group(1)], self.text[language])


def clean(value: object) -> str:
    """One line, never empty: what Meta accepts as a parameter."""
    text = _SPACE.sub(" ", str(value if value is not None else "")).strip()
    return (text or "-")[:MAX_VALUE]


_TEMPLATES = (
    # Expiry automations, before and on the day (§9).
    Template(
        "membership_ends",
        {
            "en": "Hi {name}, this is {gym}. Your {plan} membership ends on "
            "{end_date}. You can renew at the desk or in the app.",
            "ne": "नमस्ते {name}, {gym} बाट। तपाईंको {plan} सदस्यता {end_date} मा "
            "सकिन्छ। डेस्कमा वा एपबाट नवीकरण गर्न सक्नुहुन्छ।",
        },
    ),
    # Expiry automations after the day.
    Template(
        "membership_ended",
        {
            "en": "Hi {name}, this is {gym}. Your {plan} membership ended on "
            "{end_date}. You can renew at the desk or in the app.",
            "ne": "नमस्ते {name}, {gym} बाट। तपाईंको {plan} सदस्यता {end_date} मा "
            "सकियो। डेस्कमा वा एपबाट नवीकरण गर्न सक्नुहुन्छ।",
        },
    ),
    # A sale or renewal at the desk, or an app payment approved (§5.3, §5.4).
    Template(
        "membership_active",
        {
            "en": "Hi {name}, this is {gym}. Your {plan} membership is active "
            "until {end_date}. Your check-in QR is in the app.",
            "ne": "नमस्ते {name}, {gym} बाट। तपाईंको {plan} सदस्यता {end_date} सम्म "
            "सक्रिय छ। चेक-इन QR एपमा छ।",
        },
    ),
    # Money still owed on a membership (the dues automation).
    Template(
        "money_owed",
        {
            "en": "Hi {name}, this is {gym}. Rs {amount} is still to pay for your "
            "{plan} membership. You can pay at the desk or in the app.",
            "ne": "नमस्ते {name}, {gym} बाट। तपाईंको {plan} सदस्यताको रु {amount} "
            "तिर्न बाँकी छ। डेस्कमा वा एपबाट तिर्न सक्नुहुन्छ।",
        },
    ),
    # Personal training (§18.3).
    Template(
        "training_ends",
        {
            "en": "Hi {name}, this is {gym}. Your personal training with {trainer} "
            "ends on {end_date}. To keep training, renew at the desk.",
            "ne": "नमस्ते {name}, {gym} बाट। {trainer} सँगको तपाईंको पर्सनल ट्रेनिङ "
            "{end_date} मा सकिन्छ। नवीकरण डेस्कमा गर्नुहोस्।",
        },
    ),
    Template(
        "training_ended",
        {
            "en": "Hi {name}, this is {gym}. Your personal training with {trainer} "
            "ended on {end_date}. To keep training, renew at the desk.",
            "ne": "नमस्ते {name}, {gym} बाट। {trainer} सँगको तपाईंको पर्सनल ट्रेनिङ "
            "{end_date} मा सकियो। नवीकरण डेस्कमा गर्नुहोस्।",
        },
    ),
    Template(
        "training_owed",
        {
            "en": "Hi {name}, this is {gym}. Rs {amount} is still to pay for your "
            "personal training ({plan}). You can pay at the desk.",
            "ne": "नमस्ते {name}, {gym} बाट। तपाईंको पर्सनल ट्रेनिङ ({plan}) को रु "
            "{amount} तिर्न बाँकी छ। डेस्कमा तिर्न सक्नुहुन्छ।",
        },
    ),
    # Answers to what the member sent from the app (§5.4, §16.3 8.6).
    Template(
        "payment_not_confirmed",
        {
            "en": "Hi {name}, this is {gym}. We couldn't confirm your payment: "
            "{reason}. Please check, or ask at the desk.",
            "ne": "नमस्ते {name}, {gym} बाट। तपाईंको भुक्तानी पुष्टि हुन सकेन: "
            "{reason}। कृपया जाँच्नुहोस्, वा डेस्कमा सोध्नुहोस्।",
        },
    ),
    Template(
        "freeze_approved",
        {
            "en": "Hi {name}, this is {gym}. Your membership is frozen from "
            "{from_date} to {to_date}. It now ends on {end_date}. The details "
            "are in the app.",
            "ne": "नमस्ते {name}, {gym} बाट। तपाईंको सदस्यता {from_date} देखि "
            "{to_date} सम्म रोकिएको छ। अब यो {end_date} मा सकिन्छ। विवरण एपमा छ।",
        },
    ),
    Template(
        "freeze_not_approved",
        {
            "en": "Hi {name}, this is {gym}. We couldn't freeze your membership: "
            "{reason}. Please ask at the desk.",
            "ne": "नमस्ते {name}, {gym} बाट। तपाईंको सदस्यता रोक्न सकिएन: "
            "{reason}। कृपया डेस्कमा सोध्नुहोस्।",
        },
    ),
    # The welcome, with the app's link on the button (§5.5).
    Template(
        "welcome",
        {
            "en": "Welcome to {gym}, {name}! Your membership is active until "
            "{end_date}. Open the app for your check-in QR.",
            "ne": "नमस्ते {name}, {gym} मा स्वागत छ! तपाईंको सदस्यता {end_date} सम्म "
            "सक्रिय छ। चेक-इन QR का लागि एप खोल्नुहोस्।",
        },
    ),
    Template(
        "welcome_no_plan",
        {
            "en": "Welcome to {gym}, {name}! Open the app to see your membership "
            "and your check-in QR.",
            "ne": "नमस्ते {name}, {gym} मा स्वागत छ! सदस्यता र चेक-इन QR हेर्न एप खोल्नुहोस्।",
        },
    ),
    # A receipt sent from the desk, the PDF behind the button (§16.3, 8.4).
    Template(
        "receipt",
        {
            "en": "Hi {name}, this is {gym}. Here is receipt #{receipt} for "
            "Rs {amount}. Tap the button below to download it.",
            "ne": "नमस्ते {name}, {gym} बाट। रु {amount} को रसिद #{receipt} तल "
            "बटन थिचेर डाउनलोड गर्नुहोस्।",
        },
        button=Button({"en": "Download receipt", "ne": "रसिद डाउनलोड"}, "receipt"),
    ),
)

TEMPLATES: dict[str, Template] = {t.key: t for t in _TEMPLATES}
LANGUAGES = ("en", "ne")


def meta_language(language: str) -> tuple[str, str]:
    """(our language, Meta's code) to send in. Meta has no Nepali: ours is
    registered under WHATSAPP_NEPALI_LANGUAGE, or English is sent instead."""
    if language == "ne" and settings.whatsapp_nepali_language:
        return "ne", settings.whatsapp_nepali_language
    return "en", "en"


def for_rule(trigger: str, days: int) -> Template | None:
    """The template an automation sends by WhatsApp; None for marketing ones,
    which go by push and SMS only."""
    if trigger == "expiry":
        return TEMPLATES["membership_ends" if days <= 0 else "membership_ended"]
    if trigger == "dues":
        return TEMPLATES["money_owed"]
    if trigger == "pt_ending":
        return TEMPLATES["training_ends" if days <= 0 else "training_ended"]
    if trigger == "pt_dues":
        return TEMPLATES["training_owed"]
    return None


@dataclass(frozen=True)
class WhatsApp:
    """A message to send by WhatsApp where it can go: the template, our values
    for it, and the end of the button's link."""

    template: str
    values: Mapping[str, object]
    button: str | None = None

    def payload(self) -> dict:
        return {
            "template": self.template,
            "values": {k: clean(v) for k, v in self.values.items()},
            "button": self.button,
        }

    @classmethod
    def from_payload(cls, data: dict) -> "WhatsApp":
        return cls(data["template"], data["values"], data.get("button"))
