"""Item photos: anyone can see them, staff can change them."""

from typing import Annotated

from fastapi import APIRouter, Body, Response

from app.deps import DB, CurrentStaff, Now
from app.models import ItemPhoto
from app.problems import NotFound
from app.services import photos

router = APIRouter(prefix="/api")


@router.get("/items/{item_id}/photo")
def item_photo(item_id: int, db: DB) -> Response:
    """The picture itself. Its address changes when the photo does (see photo_urls),
    so the browser may keep it for a year."""
    photo = db.get(ItemPhoto, item_id)
    if photo is None:
        raise NotFound("That item has no photo.")
    return Response(
        content=photo.data,
        media_type=photo.content_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.put("/items/{item_id}/photo", status_code=204)
def set_item_photo(
    item_id: int,
    # The picture's bytes, as the whole body of the request, like a file upload.
    picture: Annotated[bytes, Body(media_type="image/jpeg")],
    staff: CurrentStaff,
    db: DB,
    now: Now,
) -> Response:
    photos.set_photo(db, item_id, picture, now)
    db.commit()
    return Response(status_code=204)


@router.delete("/items/{item_id}/photo", status_code=204)
def remove_item_photo(item_id: int, staff: CurrentStaff, db: DB) -> Response:
    photos.remove_photo(db, item_id)
    db.commit()
    return Response(status_code=204)
