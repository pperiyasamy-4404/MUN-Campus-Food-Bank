"""Packing, checked straight from app/services/packing.py.

First the refill rule (U4) on its own, with the two examples from
how-it-works.html (part 12). Then packing a bag in the database: when packing
is allowed (K1), what Packed saves, the flags in the queue (U7), and two
volunteers at the same moment. The web side is in test_packing_api.py.

The pickup day is Monday 9 November 2026. With the sample settings, booking
closes at 12 pm, pickup is 3:30 to 5:30 pm, and no-shows are at 6 pm,
St. John's time (UTC-3:30 in November).
"""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Booking,
    BookingItem,
    BookingSubstitute,
    Category,
    Item,
    PickupDay,
    Settings,
    Slot,
    Staff,
    Student,
    Variety,
)
from app.problems import NotFound, Problem
from app.sample_data import SAMPLE_SETTINGS
from app.services import booking as booking_rules
from app.services import packing, stock
from app.services.booking import Choice
from app.services.packing import (
    AlreadyPacked,
    BookedFood,
    Missing,
    NotPacked,
    PlanChanged,
    SubstituteFood,
    refill,
    sticky_note,
)
from app.services.pickup_days import make_pickup_day
from tests.helpers import MONDAY, THURSDAY, add, make_staff, make_student, wait_until_someone_is_waiting_for_a_lock

OPEN = datetime(2026, 11, 8, 21, 0, tzinfo=UTC)  # Sunday 5:30 pm: booking is open
BEFORE_PACKING = datetime(2026, 11, 9, 15, 29, tzinfo=UTC)  # Monday 11:59 am
PACKING = datetime(2026, 11, 9, 16, 0, tzinfo=UTC)  # Monday 12:30 pm
LAST_MINUTE = datetime(2026, 11, 9, 21, 29, tzinfo=UTC)  # Monday 5:59 pm
NO_SHOW = datetime(2026, 11, 9, 21, 30, tzinfo=UTC)  # Monday 6:00 pm


# ---------- the refill rule on its own (U4) ----------

# Made-up ids. Each item is a kind of food, each variety one kind of it.
OATS, PASTA, OIL, CHICKEN, BEANS, RICE, LENTILS = range(1, 8)
QUICK_OATS, STEEL_CUT_OATS, GF_PASTA, SUNFLOWER_OIL, VEGETABLE_OIL, PEANUT_OIL = 11, 12, 21, 31, 32, 33
CHUNK_CHICKEN, BLACK_BEANS, WHITE_RICE, RED_LENTILS = 41, 51, 61, 71
NAMES = {
    QUICK_OATS: "Quick oats",
    STEEL_CUT_OATS: "Steel-cut oats",
    GF_PASTA: "Gluten-free pasta",
    SUNFLOWER_OIL: "Sunflower oil",
    VEGETABLE_OIL: "Vegetable oil",
    PEANUT_OIL: "Peanut oil",
    CHUNK_CHICKEN: "Chunk chicken",
    BLACK_BEANS: "Black beans",
    WHITE_RICE: "White rice",
    RED_LENTILS: "Red lentils",
}

# The five things booked in both examples.
BOOKED = [
    BookedFood(QUICK_OATS, OATS, 1),
    BookedFood(GF_PASTA, PASTA, 1),
    BookedFood(SUNFLOWER_OIL, OIL, 1),
    BookedFood(CHUNK_CHICKEN, CHICKEN, 1),
    BookedFood(BLACK_BEANS, BEANS, 1),
]


def substitute(rank: int, variety_id: int, item_id: int, can_take: bool = True) -> SubstituteFood:
    return SubstituteFood(rank, variety_id, item_id, can_take)


def test_example_1_one_thing_is_missing():
    """Sunflower oil is gone. Rice is first, in stock, and not in the bag yet, so it goes in."""
    result = refill(
        BOOKED,
        missing=[(SUNFLOWER_OIL, 1)],
        substitutes=[substitute(1, WHITE_RICE, RICE), substitute(2, VEGETABLE_OIL, OIL), substitute(3, RED_LENTILS, LENTILS)],
        not_on_shelf=set(),
        max_per_item=1,
    )

    assert result.outcomes == {WHITE_RICE: "use", VEGETABLE_OIL: "not_needed", RED_LENTILS: "not_needed"}
    assert sticky_note(result.swaps, NAMES) == ["Sunflower oil → White rice"]


def test_example_2_substitutes_that_get_skipped():
    """Gluten-free pasta is gone. Steel-cut oats would be a second oats, rice is out, so lentils go in."""
    result = refill(
        BOOKED,
        missing=[(GF_PASTA, 1)],
        substitutes=[
            substitute(1, STEEL_CUT_OATS, OATS),
            substitute(2, WHITE_RICE, RICE, can_take=False),
            substitute(3, RED_LENTILS, LENTILS),
        ],
        not_on_shelf=set(),
        max_per_item=1,
    )

    assert result.outcomes == {STEEL_CUT_OATS: "already_has_item", WHITE_RICE: "none_left", RED_LENTILS: "use"}
    assert sticky_note(result.swaps, NAMES) == ["Gluten-free pasta → Red lentils"]


def test_any_substitute_can_fill_any_gap():
    """Example 2 again, but the quick oats ran out instead: now steel-cut oats are fine."""
    result = refill(
        BOOKED,
        missing=[(QUICK_OATS, 1)],
        substitutes=[substitute(1, STEEL_CUT_OATS, OATS), substitute(2, WHITE_RICE, RICE)],
        not_on_shelf=set(),
        max_per_item=1,
    )

    assert result.used == [STEEL_CUT_OATS]


def test_vegetable_oil_can_replace_sunflower_oil():
    """U2's own example: a different variety of the same item, listed in case it's gone."""
    result = refill(BOOKED, [(SUNFLOWER_OIL, 1)], [substitute(1, VEGETABLE_OIL, OIL)], set(), 1)

    assert sticky_note(result.swaps, NAMES) == ["Sunflower oil → Vegetable oil"]


def test_nothing_missing_means_nothing_swapped():
    result = refill(BOOKED, [], [substitute(1, WHITE_RICE, RICE)], set(), 1)

    assert result.outcomes == {WHITE_RICE: "not_needed"}
    assert result.swaps == []


def test_refilling_stops_when_the_bag_is_back_to_its_size():
    """Two gaps, filled in the order the volunteer found them. Lentils aren't needed."""
    result = refill(
        BOOKED,
        missing=[(BLACK_BEANS, 1), (SUNFLOWER_OIL, 1)],
        substitutes=[substitute(1, WHITE_RICE, RICE), substitute(2, VEGETABLE_OIL, OIL), substitute(3, RED_LENTILS, LENTILS)],
        not_on_shelf=set(),
        max_per_item=1,
    )

    assert result.outcomes[RED_LENTILS] == "not_needed"
    assert sticky_note(result.swaps, NAMES) == ["Black beans → White rice", "Sunflower oil → Vegetable oil"]


def test_when_the_substitutes_run_out_the_student_chooses_at_the_counter():
    """U6: the bag goes out one short, and the note says so."""
    result = refill(
        BOOKED,
        missing=[(SUNFLOWER_OIL, 1), (BLACK_BEANS, 1)],
        substitutes=[substitute(1, WHITE_RICE, RICE, can_take=False), substitute(2, RED_LENTILS, LENTILS)],
        not_on_shelf=set(),
        max_per_item=1,
    )

    assert sticky_note(result.swaps, NAMES) == ["Sunflower oil → Red lentils", "Black beans → choose at the counter"]


def test_two_substitutes_of_one_item_give_only_one():
    """Vegetable oil fills one gap. Peanut oil would then be a second oil, so rice fills the other."""
    result = refill(
        BOOKED,
        missing=[(SUNFLOWER_OIL, 1), (BLACK_BEANS, 1)],
        substitutes=[substitute(1, VEGETABLE_OIL, OIL), substitute(2, PEANUT_OIL, OIL), substitute(3, WHITE_RICE, RICE)],
        not_on_shelf=set(),
        max_per_item=1,
    )

    assert result.outcomes == {VEGETABLE_OIL: "use", PEANUT_OIL: "already_has_item", WHITE_RICE: "use"}


def test_a_substitute_the_volunteer_cannot_find_is_skipped():
    result = refill(
        BOOKED,
        missing=[(SUNFLOWER_OIL, 1)],
        substitutes=[substitute(1, WHITE_RICE, RICE), substitute(2, VEGETABLE_OIL, OIL)],
        not_on_shelf={WHITE_RICE},
        max_per_item=1,
    )

    assert result.outcomes == {WHITE_RICE: "not_on_shelf", VEGETABLE_OIL: "use"}


def test_with_a_limit_of_2_a_second_of_an_item_is_allowed():
    result = refill(BOOKED, [(GF_PASTA, 1)], [substitute(1, STEEL_CUT_OATS, OATS)], set(), max_per_item=2)

    assert result.used == [STEEL_CUT_OATS]


def test_part_of_a_bigger_quantity_can_be_missing():
    """2 quick oats booked, 1 on the shelf: one gap. With a limit of 2, steel-cut oats can fill it."""
    booked = [BookedFood(QUICK_OATS, OATS, 2), BookedFood(WHITE_RICE, RICE, 1)]

    result = refill(booked, [(QUICK_OATS, 1)], [substitute(1, STEEL_CUT_OATS, OATS)], set(), max_per_item=2)

    assert result.swaps == [(QUICK_OATS, STEEL_CUT_OATS)]


# ---------- a bag in the database ----------

THE_FIVE = ["quick oats", "gluten-free pasta", "sunflower oil", "chicken", "black beans"]


@pytest.fixture
def monday(db_with_sample_week) -> PickupDay:
    return make_pickup_day(db_with_sample_week, MONDAY)


@pytest.fixture
def food(db_with_sample_week) -> dict[str, Variety]:
    """The food from the examples, 5 of each."""
    db = db_with_sample_week
    pantry = add(db, Category(name="Pantry"))
    items: dict[str, Item] = {}

    def variety(item_name: str, name: str) -> Variety:
        if item_name not in items:
            items[item_name] = add(db, Item(name=item_name, category_id=pantry.id))
        return add(db, Variety(item_id=items[item_name].id, name=name, stock=5))

    return {
        "quick oats": variety("Oats", "Quick oats"),
        "steel-cut oats": variety("Oats", "Steel-cut oats"),
        "gluten-free pasta": variety("Pasta", "Gluten-free pasta"),
        "sunflower oil": variety("Cooking oil", "Sunflower oil"),
        "vegetable oil": variety("Cooking oil", "Vegetable oil"),
        "chicken": variety("Canned chicken", "Chunk chicken"),
        "black beans": variety("Beans", "Black beans"),
        "rice": variety("Rice", "White rice"),
        "lentils": variety("Lentils", "Red lentils"),
    }


@pytest.fixture
def sam(db_with_sample_week) -> Staff:
    return make_staff(db_with_sample_week, "Sam")


def book_a_bag(db, monday, food, *names: str, substitutes=("rice", "vegetable oil", "lentils")) -> Booking:
    """A student books these on Sunday evening, in the next free time."""
    student = make_student(db)
    free = db.scalars(
        select(Slot).where(Slot.pickup_day_id == monday.id, Slot.booked_count == 0).order_by(Slot.starts_at)
    ).first()
    booking_rules.hold_slot(db, student, free.id, OPEN)
    return booking_rules.book(
        db, student, [Choice(food[name].id) for name in names or THE_FIVE], [food[name].id for name in substitutes], OPEN
    )


def missing(food, *names: str) -> list[Missing]:
    return [Missing(food[name].id) for name in names]


def refused(db, kind, call):
    """Expect a refusal, and undo whatever the call did, the way the route's missing commit would."""
    with pytest.raises(kind) as refusal:
        with db.begin_nested():
            call()
    return refusal.value


# ---------- when (K1) ----------


def test_packing_starts_when_booking_closes(db, monday, food, sam):
    bag = book_a_bag(db, monday, food)

    problem = refused(db, Problem, lambda: packing.pack(db, bag.id, [], [], [], sam, BEFORE_PACKING))

    assert problem.message == (
        "Packing for Monday, November 9 starts at 12:00 p.m., when booking closes. Until then, students can still cancel."
    )


def test_a_late_bag_can_be_packed_until_the_no_show_time(db, monday, food, sam):
    """Pickup starts at 3:30, but a bag still to pack at 5:59 can be packed while the student waits."""
    bag = book_a_bag(db, monday, food)
    late = book_a_bag(db, monday, food)

    packing.pack(db, bag.id, [], [], [], sam, LAST_MINUTE)
    problem = refused(db, Problem, lambda: packing.pack(db, late.id, [], [], [], sam, NO_SHOW))

    assert bag.status == "packed"
    assert problem.message == "Pickup for Monday, November 9 is over."


def test_a_closed_day_is_not_packed(db, monday, food, sam):
    bag = book_a_bag(db, monday, food)
    monday.closed_at, monday.closed_reason = PACKING, "Snow day"

    problem = refused(db, Problem, lambda: packing.pack(db, bag.id, [], [], [], sam, PACKING))

    assert problem.message == "Monday, November 9 is closed: Snow day"


# ---------- what Packed saves ----------


def test_a_bag_with_everything_on_the_shelf(db, monday, food, sam):
    bag = book_a_bag(db, monday, food)
    stock_before = {name: variety.stock for name, variety in food.items()}

    packed = packing.pack(db, bag.id, [], [], [], sam, PACKING)

    assert (bag.status, bag.packed_at, bag.packed_by_staff_id) == ("packed", PACKING, sam.id)
    assert packed.sticky_note() == []
    assert {name: variety.stock for name, variety in food.items()} == stock_before


def test_example_1_in_the_database(db, monday, food, sam):
    """Sunflower oil is gone: rice goes in, its stock goes down by one, and the note says so."""
    bag = book_a_bag(db, monday, food)

    packing.pack(db, bag.id, missing(food, "sunflower oil"), [], [food["rice"].id], sam, PACKING)

    oil_line = db.get(BookingItem, (bag.id, food["sunflower oil"].id))
    rice_line = db.scalar(select(BookingSubstitute).where(BookingSubstitute.booking_id == bag.id, BookingSubstitute.rank == 1))
    assert oil_line.missing == 1
    assert rice_line.replaces_variety_id == food["sunflower oil"].id
    # Rice wasn't taken from stock when booking (U3), so it is now.
    assert food["rice"].stock == 4
    # Out of stock: nobody else can book it until it's counted (U7).
    assert (food["sunflower oil"].stock, food["sunflower oil"].ran_out_at) == (0, PACKING)
    assert packing.saved_note(packing.food_in(db, bag), packing.substitutes_of(db, bag)) == ["Sunflower oil → White rice"]


def test_a_substitute_with_none_left_is_skipped(db, monday, food, sam):
    """U3: the last rice is promised to another bag, so stock says 0 and this bag skips it."""
    bag = book_a_bag(db, monday, food)
    book_a_bag(db, monday, food, "rice", substitutes=())
    food["rice"].stock = 0

    plan = packing.plan(db, bag.id, missing(food, "sunflower oil"), [], PACKING)

    assert plan.refill.outcomes[food["rice"].id] == "none_left"
    assert plan.sticky_note() == ["Sunflower oil → Vegetable oil"]


def test_a_substitute_nobody_can_find_is_marked_as_ran_out(db, monday, food, sam):
    bag = book_a_bag(db, monday, food)

    packing.pack(
        db, bag.id, missing(food, "sunflower oil"), [food["rice"].id], [food["vegetable oil"].id], sam, PACKING
    )

    assert (food["rice"].stock, food["rice"].ran_out_at) == (0, PACKING)
    assert food["vegetable oil"].stock == 4


def test_a_hidden_substitute_is_skipped(db, monday, food, sam):
    bag = book_a_bag(db, monday, food)
    food["rice"].active = False

    plan = packing.plan(db, bag.id, missing(food, "sunflower oil"), [], PACKING)

    assert plan.refill.used == [food["vegetable oil"].id]


def test_when_every_substitute_is_gone_the_bag_goes_out_short(db, monday, food, sam):
    """U6: the student chooses the rest at the counter (step 7)."""
    bag = book_a_bag(db, monday, food, substitutes=("rice",))
    food["rice"].stock = 0

    packed = packing.pack(db, bag.id, missing(food, "black beans"), [], [], sam, PACKING)

    assert (packed.booked(), packed.in_bag()) == (5, 4)
    assert packing.saved_note(packing.food_in(db, bag), packing.substitutes_of(db, bag)) == [
        "Black beans → choose at the counter"
    ]


def test_working_out_the_plan_saves_nothing(db, monday, food, sam):
    bag = book_a_bag(db, monday, food)

    plan = packing.plan(db, bag.id, missing(food, "sunflower oil"), [food["rice"].id], PACKING)
    db.flush()

    assert plan.refill.used == [food["vegetable oil"].id]
    assert bag.status == "booked"
    assert (food["rice"].stock, food["rice"].ran_out_at) == (5, None)
    assert (food["sunflower oil"].stock, food["sunflower oil"].ran_out_at) == (4, None)


# ---------- only the bag's own food (U5) ----------


@pytest.mark.parametrize(
    "findings, message",
    [
        (dict(missing=["rice"]), "Only food booked for this bag can be marked as missing."),
        (dict(missing=["sunflower oil", "sunflower oil"]), "Sunflower oil is marked as missing twice."),
        (dict(not_on_shelf=["steel-cut oats"]), "Only this bag's substitutes can be marked as out of stock."),
        (dict(not_on_shelf=["rice", "rice"]), "Each substitute can be marked once."),
    ],
)
def test_only_this_bags_own_food(db, monday, food, sam, findings, message):
    bag = book_a_bag(db, monday, food)
    marked_missing = missing(food, *findings.get("missing", []))
    not_on_shelf = [food[name].id for name in findings.get("not_on_shelf", [])]

    problem = refused(db, Problem, lambda: packing.plan(db, bag.id, marked_missing, not_on_shelf, PACKING))

    assert problem.message == message


def test_no_more_can_be_missing_than_were_booked(db, monday, food, sam):
    bag = book_a_bag(db, monday, food)

    problem = refused(
        db, Problem, lambda: packing.plan(db, bag.id, [Missing(food["sunflower oil"].id, 2)], [], PACKING)
    )

    assert problem.message == "Sunflower oil: 1 were booked, so 1 to 1 can be missing."


def test_a_plan_that_changed_is_refused_and_nothing_is_saved(db, monday, food, sam):
    """The page said rice. Before Packed, another bag took the last one."""
    bag = book_a_bag(db, monday, food)
    plan = packing.plan(db, bag.id, missing(food, "sunflower oil"), [], PACKING)
    food["rice"].stock = 0
    db.flush()

    refused(
        db,
        PlanChanged,
        lambda: packing.pack(db, bag.id, missing(food, "sunflower oil"), [], plan.refill.used, sam, PACKING),
    )

    db.expire_all()
    assert db.get(Booking, bag.id).status == "booked"
    assert db.get(Variety, food["sunflower oil"].id).ran_out_at is None


# ---------- booked -> packed, once (B2) ----------


def test_a_bag_is_packed_once(db, monday, food, sam):
    bag = book_a_bag(db, monday, food)
    packing.pack(db, bag.id, [], [], [], sam, PACKING)

    problem = refused(db, AlreadyPacked, lambda: packing.pack(db, bag.id, [], [], [], make_staff(db), PACKING))

    assert problem.message == f"Bag {bag.code} is packed already, by Sam at 12:30 p.m."


def test_a_cancelled_booking_has_nothing_to_pack(db, monday, food, sam):
    bag = book_a_bag(db, monday, food)
    booking_rules.cancel(db, db.get(Student, bag.student_id), OPEN)

    problem = refused(db, Problem, lambda: packing.pack(db, bag.id, [], [], [], sam, PACKING))

    assert problem.message == f"Booking {bag.code} was cancelled, so there's nothing to pack."


def test_a_bag_that_does_not_exist(db, monday, sam):
    refused(db, NotFound, lambda: packing.pack(db, 999_999, [], [], [], sam, PACKING))


# ---------- undoing Packed (decided 7 Nov) ----------


def test_undoing_packed_puts_the_substitutes_back(db, monday, food, sam):
    bag = book_a_bag(db, monday, food)
    packing.pack(db, bag.id, missing(food, "sunflower oil"), [], [food["rice"].id], sam, PACKING)
    assert food["rice"].stock == 4

    packing.unpack(db, bag.id, sam, PACKING + timedelta(minutes=5))

    assert (bag.status, bag.packed_at, bag.packed_by_staff_id) == ("booked", None, None)
    assert food["rice"].stock == 5
    assert db.get(BookingItem, (bag.id, food["sunflower oil"].id)).missing == 0
    assert packing.saved_note(packing.food_in(db, bag), packing.substitutes_of(db, bag)) == []
    # The shelf really had no sunflower oil, so that mark stays until someone counts it.
    assert food["sunflower oil"].ran_out_at == PACKING
    logged = db.scalar(select(AuditLog).where(AuditLog.booking_id == bag.id))
    assert (logged.action, logged.staff_id) == ("undid_packed", sam.id)


def test_a_bag_can_be_packed_again_after_an_undo(db, monday, food, sam):
    bag = book_a_bag(db, monday, food)
    packing.pack(db, bag.id, [], [], [], sam, PACKING)
    packing.unpack(db, bag.id, sam, PACKING)

    packing.pack(db, bag.id, missing(food, "black beans"), [], [food["rice"].id], sam, PACKING)

    assert bag.status == "packed"
    assert packing.saved_note(packing.food_in(db, bag), packing.substitutes_of(db, bag)) == ["Black beans → White rice"]


def test_only_a_packed_bag_can_be_unpacked(db, monday, food, sam):
    bag = book_a_bag(db, monday, food)

    problem = refused(db, NotPacked, lambda: packing.unpack(db, bag.id, sam, PACKING))

    assert problem.message == f"Bag {bag.code} isn't packed."


def test_a_bag_that_was_handed_over_cannot_be_unpacked(db, monday, food, sam):
    bag = book_a_bag(db, monday, food)
    packing.pack(db, bag.id, [], [], [], sam, PACKING)
    # Step 7, the counter, will do this.
    bag.status, bag.picked_up_at, bag.picked_up_by_staff_id = "picked_up", PACKING, sam.id

    problem = refused(db, NotPacked, lambda: packing.unpack(db, bag.id, sam, PACKING))

    assert problem.message == f"Bag {bag.code} was picked up already, so Packed can't be undone."


def test_undo_ends_at_the_no_show_time(db, monday, food, sam):
    bag = book_a_bag(db, monday, food)
    packing.pack(db, bag.id, [], [], [], sam, PACKING)

    problem = refused(db, Problem, lambda: packing.unpack(db, bag.id, sam, NO_SHOW))

    assert problem.message == "Pickup for Monday, November 9 is over."


# ---------- the queue and its flags (U7) ----------


def test_when_sunflower_oil_runs_out_every_other_bag_with_it_is_flagged(db, monday, food, sam):
    first = book_a_bag(db, monday, food)
    second = book_a_bag(db, monday, food)
    no_oil = book_a_bag(db, monday, food, "quick oats", "rice", substitutes=())

    packing.pack(db, first.id, missing(food, "sunflower oil"), [], [food["rice"].id], sam, PACKING)

    flags = {bag.booking.id: bag.ran_out for bag in packing.queue(db, monday)}
    assert flags == {first.id: [], second.id: ["Sunflower oil"], no_oil.id: []}


def test_counting_the_shelf_clears_the_flag(db, monday, food, sam):
    """Someone found more at the back and counted it: the other bags aren't short any more."""
    first, second = book_a_bag(db, monday, food), book_a_bag(db, monday, food)
    packing.pack(db, first.id, missing(food, "sunflower oil"), [], [food["rice"].id], sam, PACKING)

    stock.count_shelf(db, food["sunflower oil"].id, 3, sam, PACKING + timedelta(minutes=5))

    assert food["sunflower oil"].ran_out_at is None
    assert {bag.booking.id: bag.ran_out for bag in packing.queue(db, monday)}[second.id] == []


def test_found_it_takes_the_flag_off_every_bag(db, monday, food, sam):
    """Sam marked the oil out of stock, then Jo found some at the back (decided 12 Nov)."""
    first, second, third = (book_a_bag(db, monday, food) for _ in range(3))
    packing.pack(db, first.id, missing(food, "sunflower oil"), [], [food["rice"].id], sam, PACKING)
    oil = food["sunflower oil"]

    later = PACKING + timedelta(minutes=10)
    packing.pack(db, second.id, [], [], [], sam, later, found=[oil.id])

    assert {bag.booking.id: bag.ran_out for bag in packing.queue(db, monday)}[third.id] == []
    # Nobody knows how many are left, so students still can't book it until someone checks.
    assert (oil.stock, oil.ran_out_at, oil.found_at) == (0, None, later)


def test_checking_the_shelf_after_found_it_lets_students_book_again(db, monday, food, sam):
    first, second = book_a_bag(db, monday, food), book_a_bag(db, monday, food)
    packing.pack(db, first.id, missing(food, "sunflower oil"), [], [food["rice"].id], sam, PACKING)
    oil = food["sunflower oil"]
    packing.pack(db, second.id, [], [], [], sam, PACKING, found=[oil.id])

    stock.count_shelf(db, oil.id, 4, sam, PACKING + timedelta(minutes=5))

    assert (oil.stock, oil.found_at) == (4, None)


def test_running_out_again_after_found_it_flags_the_bags_again(db, monday, food, sam):
    first, second, third, fourth = (book_a_bag(db, monday, food) for _ in range(4))
    oil = food["sunflower oil"]
    packing.pack(db, first.id, missing(food, "sunflower oil"), [], [food["rice"].id], sam, PACKING)
    packing.pack(db, second.id, [], [], [], sam, PACKING, found=[oil.id])

    later = PACKING + timedelta(minutes=20)
    packing.pack(db, third.id, missing(food, "sunflower oil"), [], [food["rice"].id], sam, later)

    assert (oil.ran_out_at, oil.found_at) == (later, None)
    assert {bag.booking.id: bag.ran_out for bag in packing.queue(db, monday)}[fourth.id] == ["Sunflower oil"]


def test_found_it_does_nothing_to_food_nobody_marked(db, monday, food, sam):
    bag = book_a_bag(db, monday, food)
    oil = food["sunflower oil"]
    before = oil.stock

    packing.pack(db, bag.id, [], [], [], sam, PACKING, found=[oil.id])

    assert (oil.stock, oil.ran_out_at, oil.found_at) == (before, None, None)


def test_only_this_bags_food_can_be_found(db, monday, food, sam):
    bag = book_a_bag(db, monday, food, "quick oats", "rice", substitutes=())

    problem = refused(
        db, Problem, lambda: packing.pack(db, bag.id, [], [], [], sam, PACKING, found=[food["sunflower oil"].id])
    )

    assert problem.message == "Only food booked for this bag can be marked as found."


def test_a_count_says_who_is_packing_that_food(db, monday, food, sam):
    """Some of it may be in Sam's bag already, not on the shelf, so the count is a little low."""
    bag = book_a_bag(db, monday, food)
    packing.start_packing(db, bag.id, sam, PACKING)

    counted = stock.count_shelf(db, food["sunflower oil"].id, 3, sam, PACKING)

    assert counted.being_packed_by == [sam.username]
    packing.pack(db, bag.id, [], [], [], sam, PACKING)
    assert stock.count_shelf(db, food["sunflower oil"].id, 3, sam, PACKING).being_packed_by == []


def test_the_queue_is_in_pickup_time_order_without_cancelled_bookings(db, monday, food, sam):
    first, cancelled, third = (book_a_bag(db, monday, food) for _ in range(3))
    booking_rules.cancel(db, db.get(Student, cancelled.student_id), OPEN)
    packing.pack(db, third.id, [], [], [], sam, PACKING)

    bags = packing.queue(db, monday)

    assert [bag.booking.id for bag in bags] == [first.id, third.id]
    assert [(bag.things, bag.packed_by) for bag in bags] == [(5, None), (5, "Sam")]


def test_which_day_is_being_packed(db, monday):
    thursday = make_pickup_day(db, THURSDAY)

    assert packing.packing_day(db, LAST_MINUTE) == monday
    assert packing.packing_day(db, NO_SHOW) == thursday
    monday.closed_at, monday.closed_reason = OPEN, "Snow day"
    assert packing.packing_day(db, PACKING) == thursday


# ---------- two volunteers at the same moment ----------


@pytest.fixture
def world(engine):
    """Committed rows for the race tests: two bags that each booked sunflower oil,
    which ran out, with rice as their first substitute. Only one rice is left."""
    with Session(engine) as db:
        db.add(Settings(**SAMPLE_SETTINGS))
        staff = Staff(username="Race packer", role="volunteer")
        category = Category(name="Race pantry")
        day = PickupDay(
            pickup_date=MONDAY + timedelta(days=901),
            booking_opens_at=PACKING - timedelta(hours=20),
            booking_closes_at=PACKING - timedelta(hours=1),
            pickup_starts_at=PACKING + timedelta(hours=3),
            pickup_ends_at=PACKING + timedelta(hours=4),
            no_show_at=PACKING + timedelta(hours=5),
        )
        db.add_all([staff, category, day])
        db.flush()
        oil = Item(name="Race oil", category_id=category.id)
        rice = Item(name="Race rice", category_id=category.id)
        slots = [Slot(pickup_day_id=day.id, starts_at=PACKING + timedelta(hours=3, minutes=10 * n), capacity=1) for n in range(2)]
        students = [Student(id_hash=letter * 64, created_by_staff_id=staff.id) for letter in "cd"]
        db.add_all([oil, rice, *slots, *students])
        db.flush()
        sunflower = Variety(item_id=oil.id, name="Race sunflower oil", stock=0)
        last_rice = Variety(item_id=rice.id, name="Race white rice", stock=1)
        db.add_all([sunflower, last_rice])
        db.flush()
        bags = []
        for code, slot, student in zip(["C2D", "D3F"], slots, students):
            bag = Booking(student_id=student.id, pickup_day_id=day.id, slot_id=slot.id, code=code)
            db.add(bag)
            db.flush()
            db.add(BookingItem(booking_id=bag.id, variety_id=sunflower.id))
            db.add(BookingSubstitute(booking_id=bag.id, rank=1, variety_id=last_rice.id))
            bags.append(bag.id)
        db.commit()
        ids = {
            "bags": bags,
            "sunflower": sunflower.id,
            "rice": last_rice.id,
            "staff": staff.id,
            "day": day.id,
            "items": [oil.id, rice.id],
            "category": category.id,
            "students": [student.id for student in students],
        }
    yield ids
    with engine.begin() as tidy:
        tidy.execute(delete(Booking).where(Booking.pickup_day_id == ids["day"]))
        tidy.execute(delete(Slot).where(Slot.pickup_day_id == ids["day"]))
        tidy.execute(delete(PickupDay).where(PickupDay.id == ids["day"]))
        tidy.execute(delete(Variety).where(Variety.id.in_([ids["sunflower"], ids["rice"]])))
        tidy.execute(delete(Item).where(Item.id.in_(ids["items"])))
        tidy.execute(delete(Category).where(Category.id == ids["category"]))
        tidy.execute(delete(Student).where(Student.id.in_(ids["students"])))
        tidy.execute(delete(Staff).where(Staff.id == ids["staff"]))
        tidy.execute(delete(Settings))


def at_the_same_moment(engine, first, second) -> dict:
    """Run first() and, while its transaction is still open, second() on another connection.

    Like the one in test_booking.py: second() should wait for a lock first()
    holds, and finish after first() commits.
    """
    results = {}

    def run_second():
        with Session(engine) as db:
            try:
                second(db)
                db.commit()
                results["second"] = "done"
            except Problem as refusal:
                results["second"] = refusal

    with Session(engine) as db:
        first(db)
        racer = threading.Thread(target=run_second)
        racer.start()
        wait_until_someone_is_waiting_for_a_lock(engine)
        db.commit()
    racer.join(timeout=10)
    return results


def test_two_bags_take_the_last_rice_at_the_same_moment(engine, world):
    """Both pages said "put in rice". Only one bag can have it (I4). The other is
    told the plan changed, and its page then says what to put in instead."""

    def pack(bag_id):
        return lambda db: packing.pack(
            db, bag_id, [Missing(world["sunflower"])], [], [world["rice"]], db.get(Staff, world["staff"]), PACKING
        )

    results = at_the_same_moment(engine, pack(world["bags"][0]), pack(world["bags"][1]))

    assert isinstance(results["second"], PlanChanged)
    with Session(engine) as check:
        assert check.get(Variety, world["rice"]).stock == 0
        statuses = check.scalars(select(Booking.status).where(Booking.id.in_(world["bags"])).order_by(Booking.id))
        assert statuses.all() == ["packed", "booked"]


def test_pressing_packed_twice_at_the_same_moment(engine, world):
    """A double tap sends two requests. The second waits for the first, then finds the bag packed."""
    bag = world["bags"][0]

    def pack(db):
        packing.pack(db, bag, [Missing(world["sunflower"])], [], [world["rice"]], db.get(Staff, world["staff"]), PACKING)

    results = at_the_same_moment(engine, pack, pack)

    assert isinstance(results["second"], AlreadyPacked)
    with Session(engine) as check:
        # Taken once, not twice.
        assert check.get(Variety, world["rice"]).stock == 0


# ---------- food with no number (decided 12 Nov) ----------


def test_a_substitute_with_no_number_is_used_and_keeps_no_number(db, monday, food, sam):
    food["rice"].stock = None
    bag = book_a_bag(db, monday, food)

    packing.pack(db, bag.id, missing(food, "sunflower oil"), [], [food["rice"].id], sam, PACKING)
    assert food["rice"].stock is None
    packing.unpack(db, bag.id, sam, PACKING + timedelta(minutes=5))

    assert food["rice"].stock is None


def test_out_of_stock_gives_food_with_no_number_a_0(db, monday, food, sam):
    """Nobody can book it any more, and "few left" goes: it's none left now (U7)."""
    food["sunflower oil"].stock, food["sunflower oil"].few_left = None, True
    bag = book_a_bag(db, monday, food)

    packing.pack(db, bag.id, missing(food, "sunflower oil"), [], [food["rice"].id], sam, PACKING)

    oil = food["sunflower oil"]
    assert (oil.stock, oil.few_left, oil.ran_out_at) == (0, False, PACKING)


# ---------- who is packing it (what-could-go-wrong problem 7, decided 12 Nov) ----------


def test_opening_a_bag_says_who_is_packing_it(db, monday, food, sam):
    bag = book_a_bag(db, monday, food)

    who = packing.start_packing(db, bag.id, sam, PACKING)

    assert (who.yours, who.by, who.since) == (True, "Sam", PACKING)
    assert (bag.packing_by_staff_id, bag.packing_started_at) == (sam.id, PACKING)
    [queued] = packing.queue(db, monday)
    assert queued.packing_by == "Sam"


def test_someone_else_opening_it_is_told_and_changes_nothing(db, monday, food, sam):
    bag = book_a_bag(db, monday, food)
    packing.start_packing(db, bag.id, sam, PACKING)

    who = packing.start_packing(db, bag.id, make_staff(db, "Jo"), PACKING + timedelta(minutes=2))

    assert (who.yours, who.by, who.since) == (False, "Sam", PACKING)
    assert bag.packing_by_staff_id == sam.id


def test_opening_your_own_bag_again_keeps_the_first_time(db, monday, food, sam):
    bag = book_a_bag(db, monday, food)
    packing.start_packing(db, bag.id, sam, PACKING)

    who = packing.start_packing(db, bag.id, sam, PACKING + timedelta(minutes=5))

    assert (who.yours, who.since) == (True, PACKING)


def test_packing_it_anyway_makes_it_yours(db, monday, food, sam):
    """Jo checked: Sam has gone home. Jo packs it."""
    bag = book_a_bag(db, monday, food)
    packing.start_packing(db, bag.id, sam, PACKING)
    jo = make_staff(db, "Jo")

    who = packing.start_packing(db, bag.id, jo, PACKING + timedelta(minutes=20), anyway=True)

    assert (who.yours, who.by) == (True, "Jo")
    assert (bag.packing_by_staff_id, bag.packing_started_at) == (jo.id, PACKING + timedelta(minutes=20))


def test_packed_and_undo_clear_who_is_packing(db, monday, food, sam):
    bag = book_a_bag(db, monday, food)
    packing.start_packing(db, bag.id, sam, PACKING)

    packing.pack(db, bag.id, [], [], [], sam, PACKING)
    assert (bag.packing_by_staff_id, bag.packing_started_at) == (None, None)
    packing.unpack(db, bag.id, sam, PACKING + timedelta(minutes=5))
    assert (bag.packing_by_staff_id, bag.packing_started_at) == (None, None)


def test_a_packed_bag_cannot_be_started(db, monday, food, sam):
    bag = book_a_bag(db, monday, food)
    packing.pack(db, bag.id, [], [], [], sam, PACKING)

    with pytest.raises(AlreadyPacked):
        packing.start_packing(db, bag.id, make_staff(db, "Jo"), PACKING)


def test_two_volunteers_open_the_same_bag_at_the_same_moment(engine, world):
    """Both pages ask at once. The second waits for the first, then sees its name.
    Without the lock both would read "nobody" and both would start packing."""
    with Session(engine) as db:
        jo = Staff(username="Race packer Jo", role="volunteer")
        db.add(jo)
        db.commit()
        jo_id = jo.id
    bag = world["bags"][0]
    answers = {}

    def first(db):
        answers["first"] = packing.start_packing(db, bag, db.get(Staff, world["staff"]), PACKING)

    def second(db):
        answers["second"] = packing.start_packing(db, bag, db.get(Staff, jo_id), PACKING)

    try:
        at_the_same_moment(engine, first, second)
        assert answers["first"].yours is True
        assert (answers["second"].yours, answers["second"].by) == (False, "Race packer")
    finally:
        with engine.begin() as tidy:
            tidy.execute(update(Booking).where(Booking.id == bag).values(packing_started_at=None, packing_by_staff_id=None))
            tidy.execute(delete(Staff).where(Staff.id == jo_id))
