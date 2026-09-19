"""Nepali mobile numbers (PLAN.md §10).

Stored as the bare ten digits, `98XXXXXXXX` or `97XXXXXXXX`, so the same
number typed as "+977 984-1234567" and "9841234567" is one number.
"""

import re

_MOBILE = re.compile(r"9[78]\d{8}")
_SEPARATORS = re.compile(r"[\s\-().]")


def normalize_phone(raw: str) -> str:
    digits = _SEPARATORS.sub("", raw)
    for prefix in ("+977", "00977", "977"):
        if digits.startswith(prefix) and len(digits) == len(prefix) + 10:
            digits = digits[len(prefix) :]
            break
    if not _MOBILE.fullmatch(digits):
        raise ValueError("Enter a Nepali mobile number, like 98XXXXXXXX.")
    return digits
