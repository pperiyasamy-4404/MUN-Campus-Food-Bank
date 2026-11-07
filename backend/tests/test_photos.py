"""Item photos: staff add or change them, anyone sees them on the food cards."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import Category, Item, ItemPhoto, Variety
from app.services import photos
from tests.helpers import add, log_in, make_staff, make_student, refused_by, stop_the_clock_at

NOW = datetime(2026, 11, 8, 18, 0, tzinfo=UTC)
# The first bytes are what count, not the rest of the file.
JPEG = b"\xff\xd8\xff\xe0" + b"pretend the rest of a photo is here"
PNG = b"\x89PNG\r\n\x1a\n" + b"rest"
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 rest"


@pytest.fixture
def oats(db) -> Item:
    item = add(db, Item(name="Oats", category_id=add(db, Category(name="Breakfast")).id))
    add(db, Variety(item_id=item.id, name="Quick oats", stock=5))
    return item


@pytest.fixture
def sam(client, db):
    stop_the_clock_at(NOW)
    sam = make_staff(db, "Sam")
    log_in(client, db, sam, NOW)
    return sam


def put_photo(client, item: Item, data: bytes, content_type: str = "image/jpeg"):
    return client.put(f"/api/items/{item.id}/photo", content=data, headers={"Content-Type": content_type})


@pytest.mark.parametrize("data, content_type", [(JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp")])
def test_the_kind_of_picture_comes_from_its_first_bytes(data, content_type):
    assert photos.picture_type(data) == content_type
    assert photos.picture_type(b"<svg>not a photo</svg>") is None


def test_staff_add_a_photo_and_anyone_sees_it(client, db, oats, sam):
    assert put_photo(client, oats, PNG, "image/jpeg").status_code == 204

    client.cookies.clear()
    [category] = client.get("/api/food").json()["bookable"]
    url = category["items"][0]["photo_url"]
    picture = client.get(url)

    assert url == f"/api/items/{oats.id}/photo?v={int(NOW.timestamp())}"
    assert picture.content == PNG
    # The kind the bytes say, not the kind the browser said.
    assert picture.headers["content-type"] == "image/png"
    # The address changes with the photo, so a browser may keep it. Everything else is never kept.
    assert picture.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert client.get("/api/food").headers["cache-control"] == "no-store"


def test_a_new_photo_replaces_the_old_one(client, db, oats, sam):
    put_photo(client, oats, JPEG)
    put_photo(client, oats, PNG)

    assert db.scalars(select(ItemPhoto.data).where(ItemPhoto.item_id == oats.id)).all() == [PNG]


@pytest.mark.parametrize(
    "data, message",
    [
        (b"<svg>a drawing that could hold a script</svg>", "Use a JPEG, PNG or WebP photo."),
        (JPEG + b"x" * photos.MOST_BYTES, "That photo is too big. Use one of 2 MB or less: a phone can share a smaller copy."),
    ],
)
def test_only_real_photos_of_2_mb_or_less(client, db, oats, sam, data, message):
    response = put_photo(client, oats, data)

    assert response.status_code == 400
    assert response.json() == {"detail": message}


def test_staff_remove_a_photo(client, db, oats, sam):
    put_photo(client, oats, JPEG)

    assert client.delete(f"/api/items/{oats.id}/photo").status_code == 204
    assert client.get(f"/api/items/{oats.id}/photo").status_code == 404
    assert client.delete(f"/api/items/{oats.id}/photo").status_code == 404


def test_only_staff_change_photos(client, db, oats):
    stop_the_clock_at(NOW)
    assert put_photo(client, oats, JPEG).status_code == 401
    log_in(client, db, make_student(db), NOW)
    assert put_photo(client, oats, JPEG).status_code == 401
    assert client.delete(f"/api/items/{oats.id}/photo").status_code == 401


def test_a_photo_for_an_item_that_does_not_exist(client, db, sam):
    response = client.put("/api/items/999999/photo", content=JPEG, headers={"Content-Type": "image/jpeg"})

    assert response.status_code == 404


def test_sample_photos_never_replace_a_chosen_one(db, oats):
    rice = add(db, Item(name="Rice", category_id=oats.category_id))
    photos.set_photo(db, rice.id, PNG, NOW)

    added = photos.add_sample_photos(db, NOW)

    assert added == ["Oats"]
    assert db.get(ItemPhoto, oats.id).content_type == "image/jpeg"
    assert db.get(ItemPhoto, rice.id).data == PNG


def test_the_database_keeps_photos_small_and_known(db, oats):
    with refused_by(db, "ck_item_photos_content_type_is_known"):
        db.add(ItemPhoto(item_id=oats.id, content_type="image/svg+xml", data=JPEG, updated_at=NOW))
    with refused_by(db, "ck_item_photos_small_enough"):
        db.add(ItemPhoto(item_id=oats.id, content_type="image/jpeg", data=b"", updated_at=NOW))
