"""Create or reset a platform admin (us), who belongs to no gym.

    docker compose exec api python -m scripts.create_platform_admin \
        --name "Ramesh" --email you@example.com

Prompts for the password so it never lands in shell history. For scripts,
--password-stdin reads it from standard input instead.
"""

import argparse
import getpass
import sys

from sqlalchemy import select

from app.core.phone import normalize_phone
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.staff import StaffUser


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True)
    parser.add_argument("--email")
    parser.add_argument("--phone")
    parser.add_argument("--password-stdin", action="store_true")
    args = parser.parse_args()
    if not args.email and not args.phone:
        parser.error("give --email or --phone")

    email = args.email.lower() if args.email else None
    phone = normalize_phone(args.phone) if args.phone else None
    password = (
        sys.stdin.readline().rstrip("\n")
        if args.password_stdin
        else getpass.getpass("Password: ")
    )
    if len(password) < 12:
        print("Use at least 12 characters for a platform admin.", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        condition = StaffUser.email == email if email else StaffUser.phone == phone
        staff = db.scalars(select(StaffUser).where(condition)).first()
        if staff is not None and not staff.is_platform_admin:
            print("That login belongs to a gym's staff account.", file=sys.stderr)
            return 1
        if staff is None:
            staff = StaffUser(is_platform_admin=True, gym_id=None)
            db.add(staff)
        staff.name = args.name
        staff.email = email
        staff.phone = phone
        staff.password_hash = hash_password(password)
        staff.is_active = True
        db.commit()
    print("Platform admin ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
