"""Add the sample food a database doesn't have yet, with its photos.

Run from backend/:  .venv\\Scripts\\python -m app.add_sample_food

For a working database made before new sample food was added (like the canned
vegetables, beans, noodles, pasta sauce, coffee and more cereals on 13 Nov).
Matched by name: food already there is never changed or added twice, and a photo
the food bank chose is never replaced. Safe to run again.
"""

from datetime import UTC, datetime

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Tag
from app.sample_data import SAMPLE_EXTRAS, SAMPLE_FOOD, TAGS, add_food
from app.services.photos import add_sample_photos


def main() -> None:
    with SessionLocal.begin() as db:
        tags = {tag.name: tag for tag in db.scalars(select(Tag))}
        for name in TAGS:
            if name not in tags:
                tags[name] = Tag(name=name)
                db.add(tags[name])
        db.flush()
        added = add_food(db, SAMPLE_FOOD, is_extra=False, tags=tags)
        added += add_food(db, SAMPLE_EXTRAS, is_extra=True, tags=tags)
        photos = add_sample_photos(db, datetime.now(UTC))
    print("Food added:", ", ".join(added) if added else "nothing (every sample food is there already)")
    print("Photos added for:", ", ".join(photos) if photos else "nothing")


if __name__ == "__main__":
    main()
