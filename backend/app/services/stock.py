"""Food and stock, for the staff stock page: checking the shelf, and adding food (I1, I2, I4, I8).

The number is optional (decided 12 Nov). A volunteer can count the shelf and
type a number, or just say "in stock" or "few left" with no number.

Plain Python with a database session, like services/accounts.py. The routes in
app/routes/stock.py commit.

Who may do what: any staff member, volunteers and the coordinator alike, can
do everything here (I8, R2). On 6 Nov categories, tags and names were for the
coordinator only. The user decided on 7 Nov that volunteers can do those too.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Booking, BookingItem, Category, Item, Staff, Tag, Variety, VarietyTag
from app.problems import NameTaken, NotFound, Problem

# A typo like 1000 instead of 10 is refused, rather than letting 1000 students book it.
MOST_ON_A_SHELF = 999


# ---------- counting the shelf (I8) ----------


@dataclass
class Count:
    variety: Variety
    # Booked by students but not packed yet: still on the shelf, but already promised.
    booked_not_packed: int
    # How many booked ones are missing from the shelf. Those bookings will need a substitute.
    short_by: int


def count_shelf(db: Session, variety_id: int, on_shelf: int, staff: Staff, now: datetime) -> Count:
    """The volunteer counted the shelf. Work out how many more students can book it.

    Items booked but not packed yet are still on the shelf, but they're already
    promised, so they're taken off: 8 on the shelf with 2 booked leaves 6 to book.
    Packed items are in bags, not on the shelf, so they aren't counted either way.
    This makes a count right even while booking is open.

    The variety's row is locked first. A student booking it at the same moment
    waits until the count is saved, then takes their one off the new number.
    Without the lock, the count could overwrite their booking and promise the
    same tin twice.
    """
    if not 0 <= on_shelf <= MOST_ON_A_SHELF:
        raise Problem(f"Type a number from 0 to {MOST_ON_A_SHELF}.")
    variety = _locked_variety(db, variety_id)
    promised = booked_not_packed(db, [variety.id]).get(variety.id, 0)
    variety.stock = max(0, on_shelf - promised)
    # With a number, students see "3 left", so "few left" isn't needed.
    variety.few_left = False
    _checked(variety, staff, now)
    return Count(variety=variety, booked_not_packed=promised, short_by=max(0, promised - on_shelf))


def no_number(db: Session, variety_id: int, few_left: bool, staff: Staff, now: datetime) -> Variety:
    """The volunteer didn't count: there's some on the shelf, maybe only a few (decided 12 Nov).

    Any number of students can book it from now on. Nothing is taken off or
    put back for it, so it can't be counted twice. If it runs out while
    packing, the packer taps Out of stock, which makes it 0 again.

    Locked like a count, so a student booking it at the same moment either
    books before (and takes one off the old number) or after (and takes nothing).
    """
    variety = _locked_variety(db, variety_id)
    variety.stock = None
    variety.few_left = few_left
    _checked(variety, staff, now)
    return variety


def _locked_variety(db: Session, variety_id: int) -> Variety:
    variety = db.scalar(
        select(Variety)
        .where(Variety.id == variety_id)
        .with_for_update()
        # Read the row again even if this session has it already: the lock is the point.
        .execution_options(populate_existing=True)
    )
    if variety is None:
        raise NotFound("There's no food with that number.")
    return variety


def _checked(variety: Variety, staff: Staff, now: datetime) -> None:
    variety.counted_at = now
    variety.counted_by_staff_id = staff.id
    # Someone looked at the shelf, so a "none on the shelf" from packing no longer applies (U7).
    variety.ran_out_at = None


def booked_not_packed(db: Session, variety_ids: list[int]) -> dict[int, int]:
    """For each variety: how many are in bookings that haven't been packed yet."""
    rows = db.execute(
        select(BookingItem.variety_id, func.sum(BookingItem.quantity))
        .join(Booking, Booking.id == BookingItem.booking_id)
        .where(Booking.status == "booked", BookingItem.variety_id.in_(variety_ids))
        .group_by(BookingItem.variety_id)
    )
    return {variety_id: int(total) for variety_id, total in rows}


# ---------- adding food (I1, I2) ----------


def add_item(
    db: Session,
    category_id: int,
    name: str,
    is_extra: bool,
    first_variety: str,
    tag_ids: list[int],
    on_shelf: int | None,
    staff: Staff,
    now: datetime,
) -> Variety:
    """A new kind of food, with its first variety. An item with no varieties would show nothing."""
    if db.get(Category, category_id) is None:
        raise NotFound("There's no category with that number.")
    item = Item(name=name, category_id=category_id, is_extra=is_extra)
    _save_name(db, item, f"There's already an item called {name}. Add a variety to it instead.")
    return add_variety(db, item.id, first_variety, tag_ids, on_shelf, staff, now)


def add_variety(
    db: Session, item_id: int, name: str, tag_ids: list[int], on_shelf: int | None, staff: Staff, now: datetime
) -> Variety:
    """A new kind of an item, like penne next to spaghetti.

    With a number, it's counted as it's added. With none (on_shelf is None),
    it's in stock with no number, like most food.
    """
    item = db.get(Item, item_id)
    if item is None:
        raise NotFound("There's no item with that number.")
    if on_shelf is not None and not 0 <= on_shelf <= MOST_ON_A_SHELF:
        raise Problem(f"Type a number from 0 to {MOST_ON_A_SHELF}.")
    tags = _tags_with_ids(db, tag_ids)
    variety = Variety(item_id=item.id, name=name, stock=on_shelf, counted_at=now, counted_by_staff_id=staff.id)
    _save_name(db, variety, f"{item.name} already has a variety called {name}.")
    db.add_all(VarietyTag(variety_id=variety.id, tag_id=tag.id) for tag in tags)
    return variety


def set_tags(db: Session, variety_id: int, tag_ids: list[int]) -> None:
    """Vegetarian, halal, gluten-free, contains nuts... (I2). Replaces the variety's tags."""
    variety = _variety(db, variety_id)
    tags = _tags_with_ids(db, tag_ids)
    db.execute(delete(VarietyTag).where(VarietyTag.variety_id == variety.id))
    db.add_all(VarietyTag(variety_id=variety.id, tag_id=tag.id) for tag in tags)


def show(db: Session, variety_id: int, shown: bool) -> None:
    """Hidden, not deleted, when the food bank stops getting it: old bookings still point to it.

    A hidden variety can't be booked. Bookings that have it already keep it (I8).
    """
    _variety(db, variety_id).active = shown


# ---------- categories, tags and names ----------


def add_category(db: Session, name: str) -> Category:
    category = Category(name=name)
    _save_name(db, category, f"There's already a category called {name}.")
    return category


def add_tag(db: Session, name: str) -> Tag:
    """Like "Vegan". A table, not a column, so this needs no code change (decided 3 Nov)."""
    tag = Tag(name=name)
    _save_name(db, tag, f"There's already a tag called {name}.")
    return tag


def rename(db: Session, kind: type[Category] | type[Item] | type[Variety], row_id: int, name: str) -> None:
    """Fix a name, like "Spagetti". Bookings point to the row, so they show the new name."""
    row = db.get(kind, row_id)
    if row is None:
        raise NotFound("There's nothing with that number.")
    _save_name(db, row, f"That name is already used: {name}.", new_name=name)


# ---------- shared steps ----------


def _save_name(
    db: Session, row: Category | Item | Variety | Tag, taken: str, new_name: str | None = None
) -> None:
    """Save the row (with its new name, for a rename). If the name is taken, say so in words.

    Names are unique ignoring capitals, by a database rule (uq_items_name_lower
    and the like), so the database decides, even if two people add "Pasta" at once.
    The savepoint means a refused name leaves the rest of the request as it was.
    The name changes inside the savepoint: opening one saves what's waiting
    first, so a change made before it would be saved outside it, and a refusal
    would break the whole request.
    """
    try:
        with db.begin_nested():
            if new_name is not None:
                row.name = new_name
            db.add(row)
            db.flush()
    except IntegrityError as error:
        rule = getattr(getattr(error.orig, "diag", None), "constraint_name", "") or ""
        if rule.startswith("uq_"):
            raise NameTaken(taken) from None
        raise


def _variety(db: Session, variety_id: int) -> Variety:
    variety = db.get(Variety, variety_id)
    if variety is None:
        raise NotFound("There's no food with that number.")
    return variety


def _tags_with_ids(db: Session, tag_ids: list[int]) -> list[Tag]:
    wanted = set(tag_ids)
    tags = list(db.scalars(select(Tag).where(Tag.id.in_(wanted)))) if wanted else []
    if len(tags) != len(wanted):
        raise NotFound("One of those tags doesn't exist.")
    return tags
