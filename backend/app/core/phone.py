"""Nepali mobile numbers (PLAN.md §10).

Stored as the bare ten digits, `98XXXXXXXX` or `97XXXXXXXX`, so the same
number typed as "+977 984-1234567" and "9841234567" is one number.
"""

import re

# [0-9], not \d: in Python \d is any digit, so "98४१२३४५६७" would pass and be
# stored as a different number from "9841234567".
_MOBILE = re.compile(r"9[78][0-9]{8}")
_SEPARATORS = re.compile(r"[\s\-().]")
_DEVANAGARI = str.maketrans("०१२३४५६७८९", "0123456789")


def ascii_digits(text: str) -> str:
    """A Nepali keyboard's ९८४१ as 9841: the same number, typed in Nepali."""
    return text.translate(_DEVANAGARI)


def normalize_phone(raw: str) -> str:
    digits = _SEPARATORS.sub("", ascii_digits(raw))
    for prefix in ("+977", "00977", "977"):
        if digits.startswith(prefix) and len(digits) == len(prefix) + 10:
            digits = digits[len(prefix) :]
            break
    if not _MOBILE.fullmatch(digits):
        raise ValueError("Enter a Nepali mobile number, like 98XXXXXXXX.")
    return digits
