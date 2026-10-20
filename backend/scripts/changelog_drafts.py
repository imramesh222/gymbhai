"""What's new drafts for what's been built, to publish from /admin (§16.5, 10.4).

    docker compose exec api python -m scripts.changelog_drafts

Adds each entry below as a draft, unless one with its title is already there
(published or not): safe to run again. Nothing is published: read each in
/admin → What's new, change it if you like, and publish it when the feature
is live for gyms (WhatsApp, for one, waits on Meta).

Written for gym owners and the desk: what they can do now, and where.
"""

import sys

from sqlalchemy import select

import app.models  # noqa: F401  (registers every table)
from app.db.session import SessionLocal
from app.models.platform import ChangelogEntry

# (title, body), oldest first: /admin lists the newest first.
DRAFTS: list[tuple[str, str]] = [
    (
        "Couple and family plans",
        "Sell one plan to two people, or a whole family, at one price.\n"
        "Settings › Plans and prices: set People to 2 for a couple (up to 6). "
        "When you sell it, add the others under “Who else is on it?”. Everyone "
        "gets their own membership and QR; the person who pays sees what's "
        "owed, and the door treats the money owed as the whole family's.",
    ),
    (
        "The door keeps working when the internet drops",
        "The kiosk at the door now keeps a list of who may come in, and keeps "
        "letting members in for up to 3 days with no internet. The visits are "
        "sent as soon as it's back online, at the times they happened.\n"
        "Change how long in Settings › Check-in rules. Members' apps update "
        "themselves to a new QR code; the phone app needs its next update.",
    ),
    (
        "Classes, booked from the app",
        "Run Zumba, yoga or any class at fixed times, with places counted.\n"
        "Settings › Classes: add your classes and the weekly timetable. "
        "Members book in their app and join a waitlist when it's full; the "
        "desk books for them under Classes. Instructors tick who came under "
        "My classes. Choose which classes each plan includes in Settings › "
        "Plans and prices.",
    ),
    (
        "Progress: weight and measurements",
        "Members can now track their weight, body fat and measurements in the "
        "app, with a chart, and keep private progress photos.\n"
        "Trainers record checks on the member's Progress tab. A member's photos "
        "stay private unless they choose to show their trainer.",
    ),
    (
        "Reminders by WhatsApp",
        "Members who agree can get their reminders and answers on WhatsApp "
        "instead of SMS, when the app's notifications can't reach them.\n"
        "Turn it on in Settings › Gym profile and calendar, then tick “Agrees "
        "to messages on WhatsApp” on each member who says yes (they can also "
        "turn it on in their app). Each message uses message credits, like an "
        "SMS; Sent messages shows when it was delivered and read. You can also "
        "send a receipt on WhatsApp from the receipt.",
    ),
    (
        "Moving a class tells everyone booked",
        "Change a class's time from Classes › the class › Change this class, "
        "and everyone booked or on its waitlist gets a notification with the "
        "new time (tick the box to send an SMS too). Their reminder moves with "
        "it.",
    ),
    (
        "Members can sign out a lost phone",
        "In their app, Me (or Profile) now lists every phone and browser "
        "they're signed in on. They can sign one out, or all the others, and "
        "that phone stops getting their notifications too.",
    ),
    (
        "Sell supplements and drinks at the desk",
        "A new Shop in the Desk menu. Add the products you sell with their "
        "prices, and if you like, how many are on the shelf. At the till, tap "
        "them into the basket, for a member or a walk-in, and take the money: "
        "a receipt is ready at once, and the money shows in Payments, Today and "
        "Reports. The shop warns you when stock runs low, and a voided sale "
        "puts its stock back.",
    ),
    (
        "eSewa, Khalti or Fonepay can confirm app payments",
        "If your gym has a merchant account with eSewa, Khalti or Fonepay, "
        "enter its keys in Settings › Payment accounts › Confirm "
        "automatically. Members who renew in the app then pay through the "
        "wallet, and their membership starts as soon as the wallet confirms "
        "the money: nobody at the desk needs to approve it. The money goes "
        "straight to your account, as always.",
    ),
    (
        "Your gym's own app in the stores",
        "Your members can now have an app with your gym's name and icon in the "
        "Play Store and App Store. Ask for it in Settings › Your own app; your "
        "gym publishes it under its own developer accounts, and we build and "
        "upload it for you.",
    ),
]


def add_drafts(db) -> list[str]:
    """The titles added now."""
    have = set(db.scalars(select(ChangelogEntry.title)))
    added = []
    for title, body in DRAFTS:
        if title in have:
            continue
        db.add(ChangelogEntry(title=title, body=body, published_at=None))
        added.append(title)
    db.flush()
    return added


def main() -> int:
    with SessionLocal() as db:
        added = add_drafts(db)
        db.commit()
    for title in added:
        print(f"draft: {title}")
    print(f"{len(added)} added; publish them from /admin → What's new.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
