"""Item photos: one per item, like a bowl of oats, shown on the students' food cards.

Any staff member can add, change or remove one on the Stock page. The photo is
checked by its first bytes, not by what the browser says it is, so only real
JPEG, PNG and WebP pictures are kept.
"""

from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Item, ItemPhoto
from app.problems import NotFound, Problem

MOST_BYTES = 2 * 1024 * 1024

# What each kind of picture starts with ("magic numbers").
_STARTS = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
]


def picture_type(data: bytes) -> str | None:
    """The kind of picture, from its first bytes, or None if it isn't one we keep."""
    for start, content_type in _STARTS:
        if data.startswith(start):
            return content_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def set_photo(db: Session, item_id: int, data: bytes, now: datetime) -> ItemPhoto:
    """Add or replace an item's photo."""
    if db.get(Item, item_id) is None:
        raise NotFound("There's no item with that number.")
    if len(data) > MOST_BYTES:
        raise Problem("That photo is too big. Use one of 2 MB or less: a phone can share a smaller copy.")
    content_type = picture_type(data)
    if content_type is None:
        raise Problem("Use a JPEG, PNG or WebP photo.")
    photo = db.get(ItemPhoto, item_id)
    if photo is None:
        photo = ItemPhoto(item_id=item_id, content_type=content_type, data=data, updated_at=now)
        db.add(photo)
    else:
        photo.content_type, photo.data, photo.updated_at = content_type, data, now
    db.flush()
    return photo


def remove_photo(db: Session, item_id: int) -> None:
    photo = db.get(ItemPhoto, item_id)
    if photo is None:
        raise NotFound("That item has no photo.")
    db.delete(photo)
    db.flush()


def photo_urls(db: Session, item_ids: list[int]) -> dict[int, str]:
    """The web address of each item's photo, for the items that have one.

    The time it was saved goes on the end, so a browser keeps a photo as long as
    it likes, and still fetches a new one the moment it changes.
    """
    rows = db.execute(select(ItemPhoto.item_id, ItemPhoto.updated_at).where(ItemPhoto.item_id.in_(item_ids)))
    return {item_id: f"/api/items/{item_id}/photo?v={int(updated_at.timestamp())}" for item_id, updated_at in rows}


# ---------- the sample photos ----------

SAMPLE_PHOTOS = Path(__file__).resolve().parent.parent / "sample_photos"


def add_sample_photos(db: Session, now: datetime) -> list[str]:
    """Give sample items a photo from app/sample_photos, like oats.jpg for Oats.

    Only items with no photo yet, so a photo the food bank chose is never replaced.
    Returns the names of the items that got one.
    """
    added = []
    for item in db.scalars(select(Item).order_by(Item.name)):
        file = SAMPLE_PHOTOS / f"{item.name.lower().replace(' ', '-')}.jpg"
        if file.exists() and db.get(ItemPhoto, item.id) is None:
            set_photo(db, item.id, file.read_bytes(), now)
            added.append(item.name)
    return added
