"""Counting the shelf and adding food, checked straight from app/services/stock.py (I1, I2, I4, I8).

The web side, and who may do what, is in test_stock_api.py.
"""

import itertools
import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

from app.models import Booking, BookingItem, Category, Item, PickupDay, Slot, Staff, Student, Tag, Variety, VarietyTag
from app.problems import NameTaken, NotFound, Problem
from app.services import stock
from tests.helpers import (
    MONDAY,
    add,
    make_booking,
    make_slot,
    make_staff,
    make_variety,
    new_hash,
    refused_by,
    wait_until_someone_is_waiting_for_a_lock,
)

NOW = datetime(2026, 11, 8, 18, 0, tzinfo=UTC)


# The times each status needs, by the booking table's rules.
STATUS_TIMES = {
    "booked": {},
    "packed": {"packed_at": NOW},
    "picked_up": {"packed_at": NOW, "picked_up_at": NOW},
    "cancelled": {"cancelled_at": NOW, "cancel_reason": "student"},
    "no_show": {"no_show_at": NOW},
}
codes = itertools.count(100)


@pytest.fixture
def slot(db) -> Slot:
    """One slot on Monday for every booking in a test."""
    return make_slot(db)


def book(db, slot: Slot, variety: Variety, status: str = "booked", quantity: int = 1) -> Booking:
    """A student's booking with this variety in it. Its stock was taken when they booked."""
    columns = dict(STATUS_TIMES[status])
    if "packed_at" in columns:
        columns["packed_by_staff_id"] = make_staff(db).id
    if status == "picked_up":
        columns["picked_up_by_staff_id"] = make_staff(db).id
    booking = make_booking(db, slot=slot, status=status, code=f"B{next(codes)}", **columns)
    add(db, BookingItem(booking_id=booking.id, variety_id=variety.id, quantity=quantity))
    return booking


# ---------- counting the shelf (I8) ----------


def test_a_count_with_nothing_booked_is_what_students_can_book(db):
    sam = make_staff(db, "Sam")
    oats = make_variety(db, stock=3)

    counted = stock.count_shelf(db, oats.id, 14, sam, NOW)

    assert oats.stock == 14
    assert (counted.booked_not_packed, counted.short_by) == (0, 0)
    assert (oats.counted_at, oats.counted_by_staff_id) == (NOW, sam.id)


def test_booked_items_still_on_the_shelf_are_taken_off(db, slot):
    """8 tins on the shelf, but 2 are booked and not packed yet: 6 more students can book."""
    oats = make_variety(db, stock=0)
    book(db, slot, oats)
    book(db, slot, oats)

    counted = stock.count_shelf(db, oats.id, 8, make_staff(db), NOW)

    assert oats.stock == 6
    assert counted.booked_not_packed == 2


@pytest.mark.parametrize("status", ["packed", "picked_up", "cancelled", "no_show"])
def test_other_bookings_are_not_on_the_shelf(db, slot, status):
    """Packed ones are in bags, picked-up ones are gone, and cancelled ones and
    no-shows have gone back to stock (I6)."""
    oats = make_variety(db, stock=0)
    book(db, slot, oats, status=status)

    stock.count_shelf(db, oats.id, 8, make_staff(db), NOW)

    assert oats.stock == 8


def test_fewer_on_the_shelf_than_were_booked(db, slot):
    """Stock never goes below zero (I4). The answer says how many bookings will need a substitute."""
    oats = make_variety(db, stock=0)
    book(db, slot, oats, quantity=3)

    counted = stock.count_shelf(db, oats.id, 1, make_staff(db), NOW)

    assert oats.stock == 0
    assert counted.short_by == 2


@pytest.mark.parametrize("on_shelf", [-1, stock.MOST_ON_A_SHELF + 1])
def test_a_count_must_be_sensible(db, on_shelf):
    oats = make_variety(db, stock=5)

    with pytest.raises(Problem, match="from 0 to 999"):
        stock.count_shelf(db, oats.id, on_shelf, make_staff(db), NOW)
    assert oats.stock == 5


def test_counting_food_that_does_not_exist(db):
    with pytest.raises(NotFound):
        stock.count_shelf(db, 999_999, 5, make_staff(db), NOW)


def test_a_count_always_says_who_made_it(db):
    """A database rule: a time with no counter, or a counter with no time, is refused."""
    oats = make_variety(db)
    with refused_by(db, "ck_varieties_count_has_a_counter"):
        oats.counted_at = NOW


def test_a_count_and_a_booking_at_the_same_moment(engine):
    """A student books the last-but-one tin while Sam saves his count. Neither may be lost.

    The booking takes its tin and holds the variety's row until it's saved. The
    count locks the same row first, so it waits, then sees the booking and takes
    it off. Without that lock, the count would read "nothing booked" and write 5
    over the booking: 5 students could book 4 tins. This test commits for real,
    on two connections, so it tidies up after itself.
    """
    with engine.begin() as setup:
        staff_id = setup.execute(insert(Staff).values(username="Race counter", role="volunteer").returning(Staff.id)).scalar_one()
        student_id = setup.execute(
            insert(Student).values(id_hash=new_hash(), created_by_staff_id=staff_id).returning(Student.id)
        ).scalar_one()
        day_id = setup.execute(
            insert(PickupDay)
            .values(
                pickup_date=MONDAY + timedelta(days=800),
                booking_opens_at=NOW,
                booking_closes_at=NOW + timedelta(hours=19),
                pickup_starts_at=NOW + timedelta(hours=22),
                pickup_ends_at=NOW + timedelta(hours=24),
                no_show_at=NOW + timedelta(hours=25),
            )
            .returning(PickupDay.id)
        ).scalar_one()
        slot_id = setup.execute(
            insert(Slot).values(pickup_day_id=day_id, starts_at=NOW, capacity=1).returning(Slot.id)
        ).scalar_one()
        category_id = setup.execute(insert(Category).values(name="Race category").returning(Category.id)).scalar_one()
        item_id = setup.execute(
            insert(Item).values(name="Race item", category_id=category_id).returning(Item.id)
        ).scalar_one()
        variety_id = setup.execute(
            # 3 left from last time. A donation came in, so Sam counts 5 on the shelf.
            insert(Variety).values(item_id=item_id, name="Race tin", stock=3).returning(Variety.id)
        ).scalar_one()

    def sam_saves_his_count():
        with Session(engine) as db:
            stock.count_shelf(db, variety_id, 5, db.get(Staff, staff_id), NOW)
            db.commit()

    try:
        with engine.begin() as student:
            # The student books: one tin off, and the row stays locked until this is saved.
            student.execute(update(Variety).where(Variety.id == variety_id).values(stock=Variety.stock - 1))
            booking_id = student.execute(
                insert(Booking)
                .values(student_id=student_id, pickup_day_id=day_id, slot_id=slot_id, code="RCE")
                .returning(Booking.id)
            ).scalar_one()
            student.execute(insert(BookingItem).values(booking_id=booking_id, variety_id=variety_id))
            sam = threading.Thread(target=sam_saves_his_count)
            sam.start()
            wait_until_someone_is_waiting_for_a_lock(engine)
        # The booking is saved here, so Sam's count can go ahead.
        sam.join(timeout=10)

        with engine.connect() as check:
            on_offer = check.execute(select(Variety.stock).where(Variety.id == variety_id)).scalar_one()
        # 5 on the shelf, 1 of them booked: 4 more students can book.
        assert on_offer == 4
    finally:
        with engine.begin() as tidy:
            tidy.execute(delete(Booking).where(Booking.pickup_day_id == day_id))
            tidy.execute(delete(Slot).where(Slot.id == slot_id))
            tidy.execute(delete(PickupDay).where(PickupDay.id == day_id))
            tidy.execute(delete(Variety).where(Variety.id == variety_id))
            tidy.execute(delete(Item).where(Item.id == item_id))
            tidy.execute(delete(Category).where(Category.id == category_id))
            tidy.execute(delete(Student).where(Student.id == student_id))
            tidy.execute(delete(Staff).where(Staff.id == staff_id))


# ---------- adding food (I1, I2) ----------


@pytest.fixture
def pantry(db):
    """A category and two tags to add food to."""
    return {
        "protein": add(db, Category(name="Protein")),
        "halal": add(db, Tag(name="Halal")),
        "vegetarian": add(db, Tag(name="Vegetarian")),
        "sam": make_staff(db, "Sam"),
    }


def tags_of(db, variety: Variety) -> set[str]:
    return set(
        db.scalars(select(Tag.name).join(VarietyTag, VarietyTag.tag_id == Tag.id).where(VarietyTag.variety_id == variety.id))
    )


def test_a_new_item_comes_with_its_first_variety(db, pantry):
    """A donation of something new: lentils, with one kind, counted as it's added."""
    lentils = stock.add_item(
        db, pantry["protein"].id, "Lentils", False, "Red lentils", [pantry["vegetarian"].id, pantry["halal"].id], 12, pantry["sam"], NOW
    )

    item = db.get(Item, lentils.item_id)
    assert (item.name, item.category_id, item.is_extra) == ("Lentils", pantry["protein"].id, False)
    assert (lentils.name, lentils.stock, lentils.active) == ("Red lentils", 12, True)
    assert (lentils.counted_at, lentils.counted_by_staff_id) == (NOW, pantry["sam"].id)
    assert tags_of(db, lentils) == {"Vegetarian", "Halal"}


def test_an_item_name_is_used_once_ignoring_capitals(db, pantry):
    stock.add_item(db, pantry["protein"].id, "Lentils", False, "Red lentils", [], 12, pantry["sam"], NOW)

    with pytest.raises(NameTaken, match="already an item called LENTILS. Add a variety to it instead."):
        stock.add_item(db, pantry["protein"].id, "LENTILS", False, "Green lentils", [], 4, pantry["sam"], NOW)
    # The refused item left nothing half-made behind.
    assert len(db.scalars(select(Variety).where(Variety.name == "Green lentils")).all()) == 0


def test_a_new_variety_of_an_item(db, pantry):
    lentils = stock.add_item(db, pantry["protein"].id, "Lentils", False, "Red lentils", [], 12, pantry["sam"], NOW)

    green = stock.add_variety(db, lentils.item_id, "Green lentils", [pantry["vegetarian"].id], 4, pantry["sam"], NOW)

    assert (green.item_id, green.stock) == (lentils.item_id, 4)
    with pytest.raises(NameTaken, match="Lentils already has a variety called green lentils."):
        stock.add_variety(db, lentils.item_id, "green lentils", [], 1, pantry["sam"], NOW)


def test_two_items_can_have_varieties_with_the_same_name(db, pantry):
    """"Canned" under chickpeas and "Canned" under beans are different food."""
    stock.add_item(db, pantry["protein"].id, "Chickpeas", False, "Canned", [], 3, pantry["sam"], NOW)
    stock.add_item(db, pantry["protein"].id, "Black beans", False, "Canned", [], 3, pantry["sam"], NOW)


def test_food_needs_a_real_category_item_and_tags(db, pantry):
    with pytest.raises(NotFound, match="no category"):
        stock.add_item(db, 999_999, "Lentils", False, "Red lentils", [], 12, pantry["sam"], NOW)
    with pytest.raises(NotFound, match="no item"):
        stock.add_variety(db, 999_999, "Red lentils", [], 12, pantry["sam"], NOW)
    with pytest.raises(NotFound, match="tags doesn't exist"):
        stock.add_item(db, pantry["protein"].id, "Lentils", False, "Red lentils", [999_999], 12, pantry["sam"], NOW)


def test_choosing_tags_replaces_the_old_ones(db, pantry):
    lentils = stock.add_item(db, pantry["protein"].id, "Lentils", False, "Red lentils", [pantry["halal"].id], 12, pantry["sam"], NOW)

    stock.set_tags(db, lentils.id, [pantry["vegetarian"].id, pantry["vegetarian"].id])

    assert tags_of(db, lentils) == {"Vegetarian"}
    stock.set_tags(db, lentils.id, [])
    assert tags_of(db, lentils) == set()


def test_hiding_and_showing_a_variety(db, pantry, slot):
    """Hidden, not deleted: bookings that have it still point to it."""
    oats = make_variety(db)
    booking = book(db, slot, oats)

    stock.show(db, oats.id, False)
    assert oats.active is False
    assert db.get(Booking, booking.id) is not None

    stock.show(db, oats.id, True)
    assert oats.active is True


# ---------- categories, tags and names ----------


def test_categories_and_tags_are_named_once(db, pantry):
    stock.add_category(db, "Bakery")
    stock.add_tag(db, "Vegan")

    with pytest.raises(NameTaken, match="already a category called bakery"):
        stock.add_category(db, "bakery")
    with pytest.raises(NameTaken, match="already a tag called VEGAN"):
        stock.add_tag(db, "VEGAN")


def test_fixing_a_name(db, pantry):
    spaghetti = stock.add_item(db, pantry["protein"].id, "Pasta", False, "Spagetti", [], 3, pantry["sam"], NOW)
    stock.add_variety(db, spaghetti.item_id, "Penne", [], 3, pantry["sam"], NOW)

    stock.rename(db, Variety, spaghetti.id, "Spaghetti")
    assert spaghetti.name == "Spaghetti"

    with pytest.raises(NameTaken):
        stock.rename(db, Variety, spaghetti.id, "penne")
    with pytest.raises(NotFound):
        stock.rename(db, Item, 999_999, "Anything")


# ---------- no number: in stock, or few left (decided 12 Nov) ----------


def test_food_can_be_in_stock_with_no_number(db):
    sam = make_staff(db, "Sam")
    oats = make_variety(db, stock=3)
    oats.ran_out_at = NOW - timedelta(hours=1)

    stock.no_number(db, oats.id, False, sam, NOW)

    assert (oats.stock, oats.few_left) == (None, False)
    assert (oats.counted_at, oats.counted_by_staff_id) == (NOW, sam.id)
    # Someone looked at the shelf, so the "out of stock" flag from packing is gone (U7).
    assert oats.ran_out_at is None


def test_a_volunteer_can_say_few_left(db):
    oats = make_variety(db, stock=None)

    stock.no_number(db, oats.id, True, make_staff(db), NOW)

    assert (oats.stock, oats.few_left) == (None, True)


def test_a_count_takes_few_left_away(db, slot):
    """Bookings made while it had no number took nothing off. A count takes them off now."""
    oats = make_variety(db, stock=None)
    oats.few_left = True
    book(db, slot, oats)

    stock.count_shelf(db, oats.id, 4, make_staff(db), NOW)

    assert (oats.stock, oats.few_left) == (3, False)


def test_marking_food_that_does_not_exist(db):
    with pytest.raises(NotFound):
        stock.no_number(db, 999_999, True, make_staff(db), NOW)


def test_new_food_with_no_number(db, pantry):
    sam = pantry["sam"]

    lentils = stock.add_item(db, pantry["protein"].id, "Lentils", False, "Red lentils", [], None, sam, NOW)

    assert (lentils.stock, lentils.few_left, lentils.counted_by_staff_id) == (None, False, sam.id)
