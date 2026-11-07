"""Give the sample food its photos, in a database made before photos existed.

Run from backend/:  .venv\\Scripts\\python -m app.add_sample_photos

Only items with no photo get one, matched by name (oats.jpg for Oats), so a
photo the food bank chose is never replaced. New databases get them from
app.sample_data already.
"""

from datetime import UTC, datetime

from app.db import SessionLocal
from app.services.photos import add_sample_photos


def main() -> None:
    with SessionLocal.begin() as db:
        added = add_sample_photos(db, datetime.now(UTC))
    print("Photos added for:", ", ".join(added) if added else "nothing (every sample item has one already)")


if __name__ == "__main__":
    main()
