"""The staff stock page: every item and variety, hidden ones too, with counts (I8, R2, R3).

Students see the food at /api/food (routes/food.py). This is the staff side,
where the food is added and checked: counted, or marked in stock or few left
with no number (decided 12 Nov).
"""

from collections import defaultdict
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Response
from pydantic import AfterValidator, BaseModel
from pydantic_core import PydanticCustomError
from sqlalchemy import func, select

from app.deps import DB, CurrentStaff, Now
from app.models import Category, Item, PickupDay, Staff, Tag, Variety, VarietyTag
from app.services import stock
from app.services.photos import photo_urls
from app.services.pickup_days import NEWFOUNDLAND, BookingStatus, booking_status

router = APIRouter(prefix="/api")

NAME_MAX = 60


def _tidy_name(typed: str) -> str:
    """'  Quick   oats ' is 'Quick oats'."""
    name = " ".join(typed.split())
    if not 1 <= len(name) <= NAME_MAX:
        raise PydanticCustomError("name", f"Use 1 to {NAME_MAX} characters.")
    return name


def _sensible_count(on_shelf: int) -> int:
    if not 0 <= on_shelf <= stock.MOST_ON_A_SHELF:
        raise PydanticCustomError("on_shelf", f"Type a number from 0 to {stock.MOST_ON_A_SHELF}.")
    return on_shelf


FoodName = Annotated[str, AfterValidator(_tidy_name)]
# How many are on the shelf right now.
OnShelf = Annotated[int, AfterValidator(_sensible_count)]


# ---------- what goes out ----------


class VarietyRow(BaseModel):
    id: int
    name: str
    shown: bool
    # How many more students can book it. None: not counted, any number can book it.
    stock: int | None
    # A volunteer saw only a few on the shelf. Only for food with no number.
    few_left: bool
    # Booked, not packed yet: still on the shelf, already promised.
    booked_not_packed: int
    tag_ids: list[int]
    counted_at: datetime | None
    counted_by: str | None
    # A volunteer packing a bag found none on the shelf. Cleared by the next check (U7).
    ran_out_at: datetime | None
    # Then another volunteer found some (Found it). Still 0 until the next check.
    found_at: datetime | None


class ItemRow(BaseModel):
    id: int
    name: str
    is_extra: bool
    photo_url: str | None
    varieties: list[VarietyRow]


class CategoryRow(BaseModel):
    id: int
    name: str
    items: list[ItemRow]


class TagOut(BaseModel):
    id: int
    name: str


class NextBooking(BaseModel):
    pickup_date: date
    booking_opens_at: datetime
    booking_closes_at: datetime
    booking_status: BookingStatus


class StockPage(BaseModel):
    # Every category, A to Z, empty ones too, so food can be added to them.
    categories: list[CategoryRow]
    tags: list[TagOut]
    # The next pickup day students can still book, if there is one.
    next_booking: NextBooking | None
    # When the last pickup day ended (its no-show time). A count from before then
    # is out of date: pickups and walk-ins have changed the shelf since.
    last_pickup_ended_at: datetime | None


@router.get("/stock")
def stock_page(staff: CurrentStaff, db: DB, now: Now) -> StockPage:
    categories = db.scalars(select(Category).order_by(func.lower(Category.name))).all()
    items = db.scalars(select(Item).order_by(func.lower(Item.name))).all()
    varieties = db.scalars(select(Variety).order_by(func.lower(Variety.name))).all()

    # A few questions for everything, not one per variety.
    variety_ids = [variety.id for variety in varieties]
    tags_by_variety: dict[int, list[int]] = defaultdict(list)
    for variety_id, tag_id in db.execute(select(VarietyTag.variety_id, VarietyTag.tag_id)):
        tags_by_variety[variety_id].append(tag_id)
    promised = stock.booked_not_packed(db, variety_ids)
    counter_ids = {variety.counted_by_staff_id for variety in varieties if variety.counted_by_staff_id}
    counters = {staff_id: name for staff_id, name in db.execute(select(Staff.id, Staff.username).where(Staff.id.in_(counter_ids)))}

    varieties_by_item: dict[int, list[VarietyRow]] = defaultdict(list)
    for variety in varieties:
        varieties_by_item[variety.item_id].append(
            variety_row(variety, tags_by_variety[variety.id], promised.get(variety.id, 0), counters)
        )
    urls = photo_urls(db, [item.id for item in items])
    items_by_category: dict[int, list[ItemRow]] = defaultdict(list)
    for item in items:
        items_by_category[item.category_id].append(
            ItemRow(
                id=item.id,
                name=item.name,
                is_extra=item.is_extra,
                photo_url=urls.get(item.id),
                varieties=varieties_by_item[item.id],
            )
        )

    return StockPage(
        categories=[
            CategoryRow(id=category.id, name=category.name, items=items_by_category[category.id])
            for category in categories
        ],
        tags=[TagOut(id=tag.id, name=tag.name) for tag in db.scalars(select(Tag).order_by(func.lower(Tag.name)))],
        next_booking=next_booking(db, now),
        last_pickup_ended_at=_newfoundland(
            db.scalar(
                select(func.max(PickupDay.no_show_at)).where(
                    PickupDay.no_show_at <= now, PickupDay.closed_reason.is_(None)
                )
            )
        ),
    )


def variety_row(variety: Variety, tag_ids: list[int], promised: int, counters: dict[int, str]) -> VarietyRow:
    return VarietyRow(
        id=variety.id,
        name=variety.name,
        shown=variety.active,
        stock=variety.stock,
        few_left=variety.few_left,
        booked_not_packed=promised,
        tag_ids=sorted(tag_ids),
        counted_at=_newfoundland(variety.counted_at),
        counted_by=counters.get(variety.counted_by_staff_id) if variety.counted_by_staff_id else None,
        ran_out_at=_newfoundland(variety.ran_out_at),
        found_at=_newfoundland(variety.found_at),
    )


def next_booking(db: DB, now: datetime) -> NextBooking | None:
    day = db.scalar(
        select(PickupDay)
        .where(PickupDay.booking_closes_at > now, PickupDay.closed_reason.is_(None))
        .order_by(PickupDay.pickup_date)
        .limit(1)
    )
    if day is None:
        return None
    return NextBooking(
        pickup_date=day.pickup_date,
        booking_opens_at=day.booking_opens_at.astimezone(NEWFOUNDLAND),
        booking_closes_at=day.booking_closes_at.astimezone(NEWFOUNDLAND),
        booking_status=booking_status(day, now),
    )


def _newfoundland(moment: datetime | None) -> datetime | None:
    return moment.astimezone(NEWFOUNDLAND) if moment else None


# ---------- counting the shelf (any staff) ----------


class ShelfCount(BaseModel):
    on_shelf: OnShelf


class Counted(BaseModel):
    variety: VarietyRow
    # Booked ones missing from the shelf: those bookings will need a substitute.
    short_by: int
    # Who has a bag with this food open right now: the count may be a little low.
    being_packed_by: list[str]


@router.post("/varieties/{variety_id}/count")
def count_shelf(variety_id: int, count: ShelfCount, staff: CurrentStaff, db: DB, now: Now) -> Counted:
    counted = stock.count_shelf(db, variety_id, count.on_shelf, staff, now)
    db.commit()
    tag_ids = list(db.scalars(select(VarietyTag.tag_id).where(VarietyTag.variety_id == variety_id)))
    row = variety_row(counted.variety, tag_ids, counted.booked_not_packed, {staff.id: staff.username})
    return Counted(variety=row, short_by=counted.short_by, being_packed_by=counted.being_packed_by)


class NoNumber(BaseModel):
    few_left: bool


@router.post("/varieties/{variety_id}/in-stock")
def in_stock(variety_id: int, level: NoNumber, staff: CurrentStaff, db: DB, now: Now) -> VarietyRow:
    """In stock with no number, or "few left" (decided 12 Nov)."""
    variety = stock.no_number(db, variety_id, level.few_left, staff, now)
    db.commit()
    tag_ids = list(db.scalars(select(VarietyTag.tag_id).where(VarietyTag.variety_id == variety_id)))
    promised = stock.booked_not_packed(db, [variety_id]).get(variety_id, 0)
    return variety_row(variety, tag_ids, promised, {staff.id: staff.username})


# ---------- adding food (any staff) ----------


class NewVariety(BaseModel):
    name: FoodName
    tag_ids: list[int] = []
    # Left out (or null) for food that won't be counted: it's in stock with no number.
    on_shelf: OnShelf | None = None


class NewItem(BaseModel):
    category_id: int
    name: FoodName
    is_extra: bool
    # Every item needs at least one variety. If there's only one kind, it can share the item's name.
    first_variety: NewVariety


class Added(BaseModel):
    id: int


@router.post("/items", status_code=201)
def add_item(details: NewItem, staff: CurrentStaff, db: DB, now: Now) -> Added:
    first = details.first_variety
    variety = stock.add_item(
        db, details.category_id, details.name, details.is_extra, first.name, first.tag_ids, first.on_shelf, staff, now
    )
    db.commit()
    return Added(id=variety.item_id)


@router.post("/items/{item_id}/varieties", status_code=201)
def add_variety(item_id: int, details: NewVariety, staff: CurrentStaff, db: DB, now: Now) -> Added:
    variety = stock.add_variety(db, item_id, details.name, details.tag_ids, details.on_shelf, staff, now)
    db.commit()
    return Added(id=variety.id)


class Tags(BaseModel):
    tag_ids: list[int]


@router.put("/varieties/{variety_id}/tags", status_code=204)
def set_tags(variety_id: int, tags: Tags, staff: CurrentStaff, db: DB) -> Response:
    stock.set_tags(db, variety_id, tags.tag_ids)
    db.commit()
    return Response(status_code=204)


@router.post("/varieties/{variety_id}/hide", status_code=204)
def hide(variety_id: int, staff: CurrentStaff, db: DB) -> Response:
    stock.show(db, variety_id, False)
    db.commit()
    return Response(status_code=204)


@router.post("/varieties/{variety_id}/show", status_code=204)
def show(variety_id: int, staff: CurrentStaff, db: DB) -> Response:
    stock.show(db, variety_id, True)
    db.commit()
    return Response(status_code=204)


# ---------- categories, tags and names (any staff, decided 7 Nov) ----------


class NewName(BaseModel):
    name: FoodName


@router.post("/categories", status_code=201)
def add_category(details: NewName, staff: CurrentStaff, db: DB) -> Added:
    category = stock.add_category(db, details.name)
    db.commit()
    return Added(id=category.id)


@router.post("/tags", status_code=201)
def add_tag(details: NewName, staff: CurrentStaff, db: DB) -> Added:
    tag = stock.add_tag(db, details.name)
    db.commit()
    return Added(id=tag.id)


@router.patch("/categories/{row_id}", status_code=204)
def rename_category(row_id: int, details: NewName, staff: CurrentStaff, db: DB) -> Response:
    stock.rename(db, Category, row_id, details.name)
    db.commit()
    return Response(status_code=204)


@router.patch("/items/{row_id}", status_code=204)
def rename_item(row_id: int, details: NewName, staff: CurrentStaff, db: DB) -> Response:
    stock.rename(db, Item, row_id, details.name)
    db.commit()
    return Response(status_code=204)


@router.patch("/varieties/{row_id}", status_code=204)
def rename_variety(row_id: int, details: NewName, staff: CurrentStaff, db: DB) -> Response:
    stock.rename(db, Variety, row_id, details.name)
    db.commit()
    return Response(status_code=204)
