"""Remove the gyms that end-to-end runs left in this database.

    docker compose exec api python -m scripts.purge_e2e        # what it would delete
    docker compose exec api python -m scripts.purge_e2e --yes  # delete it

`make e2e` now runs against its own database, so this is for cleaning up runs
made before that. Only gyms whose address starts with `e2e-` are touched: the
gyms you signed up yourself are left alone, and without --yes the whole thing
is rolled back, so the dry run proves the delete works before it is kept.
"""

import argparse
import sys

from sqlalchemy import delete, func, select

import app.models  # noqa: F401  (registers every table)
from app.db.base import Base
from app.db.session import SessionLocal
from app.models.gym import Gym

PREFIX = "e2e-"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--yes", action="store_true", help="keep the deletions (otherwise rolled back)"
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        gyms = db.scalars(select(Gym).where(Gym.slug.startswith(PREFIX))).all()
        total = db.scalar(select(func.count()).select_from(Gym)) or 0
        if not gyms:
            print(f"No gyms start with {PREFIX!r}. Nothing to do ({total} gyms).")
            return 0
        print(f"{len(gyms)} of {total} gyms start with {PREFIX!r}:")
        for gym in gyms[:5]:
            print(f"  {gym.name}  /{gym.slug}")
        if len(gyms) > 5:
            print(f"  ... and {len(gyms) - 5} more")

        ids = [gym.id for gym in gyms]
        removed: dict[str, int] = {}
        # Children before parents: sorted_tables is parents first.
        for table in reversed(Base.metadata.sorted_tables):
            if "gym_id" not in table.c:
                continue
            count = db.execute(delete(table).where(table.c.gym_id.in_(ids))).rowcount
            if count:
                removed[table.name] = count
        removed["gyms"] = db.execute(
            delete(Gym.__table__).where(Gym.id.in_(ids))
        ).rowcount

        for name, count in sorted(removed.items(), key=lambda row: -row[1]):
            print(f"  {count:>7} {name}")

        if not args.yes:
            db.rollback()
            print(
                "\nDry run: nothing was deleted. Add --yes to keep it.", file=sys.stderr
            )
            return 0
        db.commit()
        print("\nDeleted.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
