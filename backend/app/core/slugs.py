"""Gym slugs: the `fitness-zone` in app.gymbhai.com/fitness-zone (PLAN.md §3).

The member app lives at the top level of the web app, so a slug must never
collide with one of our own routes. Adding a top-level route in the frontend
means adding its name here first — otherwise a gym can register it and one of
the two pages becomes unreachable.
"""

import re

SLUG_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])")

RESERVED_SLUGS = frozenset(
    {
        # Routes in the frontend today or planned in PLAN.md
        "admin",
        "api",
        "kiosk",
        "login",
        "signup",
        "staff",
        # Framework and web plumbing
        "_next",
        "favicon.ico",
        "manifest.webmanifest",
        "robots.txt",
        "sitemap.xml",
        "static",
        # Paths inside the member app's API (/api/v1/m/...)
        "auth",
        "notices",
        "payment-requests",
        "renew",
        # Names people would reasonably expect to be ours
        "about",
        "account",
        "app",
        "blog",
        "contact",
        "docs",
        "gymbhai",
        "help",
        "legal",
        "pricing",
        "privacy",
        "register",
        "support",
        "terms",
        "www",
    }
)


def check_slug(value: str) -> str:
    value = value.strip().lower()
    if not SLUG_PATTERN.fullmatch(value) or "--" in value:
        raise ValueError(
            "Use 3 to 40 lowercase letters, numbers and single hyphens, "
            "starting and ending with a letter or number."
        )
    if value in RESERVED_SLUGS:
        raise ValueError("That address is reserved. Choose another.")
    return value
