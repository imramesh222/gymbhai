"""SMS text: how many messages a text costs, and filling in templates.

An SMS in the GSM alphabet holds 160 characters, or 153 per part once split.
Anything outside it — Nepali (Devanagari) above all — makes the whole message
Unicode: 70 characters, or 67 per part (PLAN.md §10). Credits are counted in
parts, so the template editor shows this before saving.
"""

import re
from collections.abc import Mapping

# The GSM 03.38 basic set, plus the extension table (which costs 2 each).
_GSM = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
_GSM_EXTENDED = set("^{}\\[~]|€")

_PLACEHOLDER = re.compile(r"\{(\w+)\}")

# What a template may use. Unknown placeholders are left as typed, so a
# mistake shows up in the preview instead of breaking the send.
PLACEHOLDERS = ("name", "gym", "plan", "end_date", "days", "link", "code", "amount")


def is_gsm(text: str) -> bool:
    return all(ch in _GSM or ch in _GSM_EXTENDED for ch in text)


def segments(text: str) -> int:
    if not text:
        return 0
    if is_gsm(text):
        length = sum(2 if ch in _GSM_EXTENDED else 1 for ch in text)
        single, part = 160, 153
    else:
        # UTF-16 code units: most Devanagari is one each.
        length = len(text.encode("utf-16-le")) // 2
        single, part = 70, 67
    if length <= single:
        return 1
    return -(-length // part)


def render(template: str, values: Mapping[str, object]) -> str:
    def fill(match: re.Match[str]) -> str:
        key = match.group(1)
        return (
            str(values[key])
            if key in values and values[key] is not None
            else match.group(0)
        )

    return _PLACEHOLDER.sub(fill, template)
