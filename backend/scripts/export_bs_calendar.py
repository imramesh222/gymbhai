"""Write the BS calendar table the frontend converts dates with.

    python -m scripts.export_bs_calendar ../frontend/src/lib/bs-calendar.json

Both sides then convert from the same data, so a date never reads one way on
a receipt and another on screen.
"""

import json
import sys

from app.core.calendar import bs_table


def main() -> None:
    path = sys.argv[1]
    with open(path, "w") as out:
        json.dump(bs_table(), out, separators=(",", ":"))
        out.write("\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
