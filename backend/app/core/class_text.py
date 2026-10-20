"""What class notifications say to members, in each language (PLAN.md §19.4).

Beside the SMS wording (app/core/sms_defaults.py): the server writes them in
the member's own language. Short, for a lock screen.
"""

# An hour before a class they booked. {class} is its name, {time} "07:00".
REMINDER: dict[str, str] = {
    "en": "{class} at {time} today. See you there!",
    "ne": "आज {time} मा {class}। भेटौँला!",
}

# A place opened up and the waitlist gave it to them.
PROMOTED: dict[str, str] = {
    "en": "A place opened up: you're booked for {class}, {day} at {time}.",
    "ne": "ठाउँ खाली भयो: {day} {time} को {class} मा तपाईंको बुकिङ भयो।",
}

# The gym cancelled a class they had booked.
CANCELLED: dict[str, str] = {
    "en": "{class}, {day} at {time}, is cancelled. {reason}",
    "ne": "{day} {time} को {class} रद्द भयो। {reason}",
}
