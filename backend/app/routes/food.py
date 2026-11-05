"""The food on the shelf, grouped by category and item. Read only."""

from collections import defaultdict

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.deps import DB
from app.models import Category, Item, Tag, Variety, VarietyTag

router = APIRouter(prefix="/api")


class VarietyOut(BaseModel):
    name: str
    # None for extras: they only show as "may be available" (E2).
    stock: int | None
    tags: list[str]


class ItemOut(BaseModel):
    name: str
    varieties: list[VarietyOut]


class CategoryOut(BaseModel):
    name: str
    items: list[ItemOut]


class FoodOut(BaseModel):
    # Booked online, up to the item limit (I3).
    bookable: list[CategoryOut]
    # Asked for at pickup, not booked online (E1).
    extras: list[CategoryOut]


# category name -> item name -> its varieties
Shelf = dict[str, dict[str, list[VarietyOut]]]


@router.get("/food")
def food_on_the_shelf(db: DB) -> FoodOut:
    """Every variety still on the list, A to Z. Hidden varieties (active = false) are left out.

    An item with no varieties left on the list doesn't appear, and neither does
    a category with no items.
    """
    rows = db.execute(
        select(
            Category.name.label("category"),
            Item.name.label("item"),
            Item.is_extra,
            Variety.id,
            Variety.name,
            Variety.stock,
        )
        .join(Item, Item.category_id == Category.id)
        .join(Variety, Variety.item_id == Item.id)
        .where(Variety.active)
        .order_by(func.lower(Category.name), func.lower(Item.name), func.lower(Variety.name))
    ).all()

    # One query for all the tags, not one per variety.
    tags_by_variety: dict[int, list[str]] = defaultdict(list)
    tag_rows = db.execute(
        select(VarietyTag.variety_id, Tag.name)
        .join(Tag, Tag.id == VarietyTag.tag_id)
        .where(VarietyTag.variety_id.in_([row.id for row in rows]))
        .order_by(func.lower(Tag.name))
    )
    for variety_id, tag_name in tag_rows:
        tags_by_variety[variety_id].append(tag_name)

    # The rows are already in order, and dicts keep the order things were added in.
    bookable: Shelf = {}
    extras: Shelf = {}
    for row in rows:
        shelf = extras if row.is_extra else bookable
        variety = VarietyOut(
            name=row.name,
            stock=None if row.is_extra else row.stock,
            tags=tags_by_variety[row.id],
        )
        shelf.setdefault(row.category, {}).setdefault(row.item, []).append(variety)

    return FoodOut(bookable=as_categories(bookable), extras=as_categories(extras))


def as_categories(shelf: Shelf) -> list[CategoryOut]:
    return [
        CategoryOut(
            name=category,
            items=[ItemOut(name=item, varieties=varieties) for item, varieties in items.items()],
        )
        for category, items in shelf.items()
    ]
