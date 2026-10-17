"""Print a new VAPID private key for Web Push (PLAN.md §16.3, 8.3).

    python -m scripts.vapid_keys

Put it in .env as VAPID_PRIVATE_KEY. Changing it later means every member has
to turn reminders on again on their phone.
"""

from app.core.push_keys import generate

if __name__ == "__main__":
    print(f"VAPID_PRIVATE_KEY={generate()}")
