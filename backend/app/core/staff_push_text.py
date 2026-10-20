"""What staff notifications say, in each language (PLAN.md §18.6).

Beside the SMS wording (app/core/sms_defaults.py) for the same reason: the
server writes them, in the staff member's own language. Short: a phone's lock
screen shows a line or two. Amounts and dates as the SMS have them.
"""

# A member sent "I've paid" from the app: one waiting, or several.
PAYMENT_TITLE: dict[str, str] = {
    "en": "Payment to approve",
    "ne": "स्वीकृत गर्नुपर्ने एप भुक्तानी",
}
PAYMENTS_TITLE: dict[str, str] = {
    "en": "{count} payments to approve",
    "ne": "स्वीकृत गर्नुपर्ने {count} एप भुक्तानी",
}
PAYMENT_BODY: dict[str, str] = {
    "en": "{name}: {amount} for {plan}",
    "ne": "{name}: {plan} का लागि {amount}",
}

# A member asked to freeze their membership.
FREEZE_TITLE: dict[str, str] = {"en": "Freeze request", "ne": "फ्रिज अनुरोध"}
FREEZES_TITLE: dict[str, str] = {
    "en": "{count} freeze requests",
    "ne": "{count} फ्रिज अनुरोध",
}
FREEZE_BODY: dict[str, str] = {
    "en": "{name}: {days} days from {date}",
    "ne": "{name}: {date} देखि {days} दिन",
}
FREEZE_BODY_ONE_DAY: dict[str, str] = {
    "en": "{name}: 1 day, {date}",
    "ne": "{name}: {date}, 1 दिन",
}

# Someone asked to join from the gym's QR.
LEAD_TITLE: dict[str, str] = {"en": "New enquiry", "ne": "नयाँ सोधपुछ"}
LEAD_BODY: dict[str, str] = {"en": "{name}, {phone}", "ne": "{name}, {phone}"}
LEAD_BODY_PLAN: dict[str, str] = {
    "en": "{name}, {phone}: {plan}",
    "ne": "{name}, {phone}: {plan}",
}
