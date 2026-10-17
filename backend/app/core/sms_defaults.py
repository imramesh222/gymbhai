"""The SMS wording a gym starts with, in each language (PLAN.md §10, §16.6).

A gym edits its own wording freely. These are only where it starts, and what
it switches to when it changes language without having edited them. Nepali is
Unicode: 70 characters an SMS rather than 160, so these are kept short.
"""

from typing import Literal

Language = Literal["en", "ne"]

WELCOME: dict[str, str] = {
    "en": "Welcome to {gym}, {name}! Active until {end_date}. "
    "Your app and check-in QR: {link}",
    "ne": "{gym} मा स्वागत छ, {name}! {end_date} सम्म सक्रिय। एप र QR: {link}",
}

MEMBERSHIP: dict[str, str] = {
    "en": "{gym}: your {plan} membership is active until {end_date}. App: {link}",
    "ne": "{gym}: तपाईंको {plan} सदस्यता {end_date} सम्म सक्रिय छ। एप: {link}",
}

# Welcome for someone added without a membership.
WELCOME_NO_PLAN: dict[str, str] = {
    "en": "Welcome to {gym}, {name}! Your app: {link}",
    "ne": "{gym} मा स्वागत छ, {name}! तपाईंको एप: {link}",
}

# (trigger, days, wording, on at sign-up), in the order they're seeded.
RULES: dict[str, list[tuple[str, int, str, bool]]] = {
    "en": [
        (
            "expiry",
            -7,
            "Hi {name}, your {plan} membership at {gym} ends on {end_date}. "
            "Renew any time at the desk or in your app: {link}",
            True,
        ),
        (
            "expiry",
            -3,
            "Hi {name}, {days} days left on your {gym} membership. Renew: {link}",
            True,
        ),
        (
            "expiry",
            0,
            "Hi {name}, your {gym} membership ends today. "
            "Renew to keep training: {link}",
            True,
        ),
        (
            "expiry",
            3,
            "Hi {name}, your {gym} membership ended on {end_date}. "
            "We miss you! Renew at the desk or here: {link}",
            True,
        ),
        (
            "lapsed",
            30,
            "Hi {name}, we haven't seen you at {gym} since your membership ended. "
            "Come back any time: {link}",
            False,
        ),
        (
            "dues",
            7,
            "Hi {name}, a reminder from {gym}: Rs {amount} is still to pay. "
            "Pay at the desk or in your app: {link}",
            False,
        ),
        (
            "not_visiting",
            14,
            "Hi {name}, we've missed you at {gym}! It's been {days} days. "
            "Your membership runs until {end_date}.",
            False,
        ),
        (
            "birthday",
            0,
            "Happy birthday, {name}! Have a great day. From all of us at {gym}",
            False,
        ),
    ],
    "ne": [
        (
            "expiry",
            -7,
            "नमस्ते {name}, {gym} को सदस्यता {end_date} मा सकिँदैछ। नवीकरण: {link}",
            True,
        ),
        (
            "expiry",
            -3,
            "नमस्ते {name}, {gym} को सदस्यतामा {days} दिन बाँकी। नवीकरण: {link}",
            True,
        ),
        (
            "expiry",
            0,
            "नमस्ते {name}, {gym} को सदस्यता आज सकिन्छ। नवीकरण: {link}",
            True,
        ),
        (
            "expiry",
            3,
            "नमस्ते {name}, {gym} को सदस्यता सकियो। हामी सम्झिरहेका छौं! {link}",
            True,
        ),
        (
            "lapsed",
            30,
            "नमस्ते {name}, {gym} मा फेरि आउनुहोस्, हामी पर्खिरहेका छौं: {link}",
            False,
        ),
        (
            "dues",
            7,
            "नमस्ते {name}, {gym} मा रु {amount} तिर्न बाँकी छ। तिर्नुहोस्: {link}",
            False,
        ),
        (
            "not_visiting",
            14,
            "नमस्ते {name}, {gym} मा {days} दिनदेखि देखिनुभएन। हामी सम्झिरहेका छौं!",
            False,
        ),
        ("birthday", 0, "जन्मदिनको शुभकामना, {name}! — {gym} परिवार", False),
    ],
}


def other(language: str) -> str:
    return "ne" if language == "en" else "en"
