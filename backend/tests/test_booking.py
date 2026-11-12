"""Holding, booking and cancelling, checked straight from app/services/booking.py.

The pickup day is Monday 9 November 2026. With the sample settings, booking
opens Sunday 8 November at 5 pm and closes Monday at 12 pm, St. John's time.
The web side is in test_booking_api.py.
"""

import re
import threading
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.models import (
    Booking,
    BookingItem,
    BookingSubstitute,
    Category,
    Hold,
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
from app.services import booking as rules
from app.services.booking import AlreadyBooked, Choice, TimeTaken
from app.services.pickup_days import make_pickup_day
from tests.helpers import MONDAY, add, make_student, wait_until_someone_is_waiting_for_a_lock

BEFORE_OPEN = datetime(2026, 11, 8, 20, 29, tzinfo=UTC)  # Sunday 4:59 pm
OPEN = datetime(2026, 11, 8, 21, 0, tzinfo=UTC)  # Sunday 5:30 pm
CLOSED = datetime(2026, 11, 9, 15, 30, tzinfo=UTC)  # Monday 12:00 pm


@pytest.fixture
def monday(db_with_sample_week) -> PickupDay:
    """Monday's pickup day, with its 12 slots of 1 place each."""
    return make_pickup_day(db_with_sample_week, MONDAY)


def slots_of(db, day: PickupDay) -> list[Slot]:
    return list(db.scalars(select(Slot).where(Slot.pickup_day_id == day.id).order_by(Slot.starts_at)))


@pytest.fixture
def food(db_with_sample_week):
    """Oats in two kinds, chicken, rice, and bread (an extra)."""
    db = db_with_sample_week
    breakfast = add(db, Category(name="Breakfast"))
    oats = add(db, Item(name="Oats", category_id=breakfast.id))
    chicken = add(db, Item(name="Canned chicken", category_id=breakfast.id))
    rice = add(db, Item(name="Rice", category_id=breakfast.id))
    bread = add(db, Item(name="Bread", category_id=breakfast.id, is_extra=True))
    return {
        "quick oats": add(db, Variety(item_id=oats.id, name="Quick oats", stock=5)),
        "steel-cut oats": add(db, Variety(item_id=oats.id, name="Steel-cut oats", stock=5)),
        "chicken": add(db, Variety(item_id=chicken.id, name="Chunk chicken", stock=2)),
        "rice": add(db, Variety(item_id=rice.id, name="White rice", stock=5)),
        "bread": add(db, Variety(item_id=bread.id, name="White bread", stock=5)),
    }


def refused(db, kind, call):
    """Expect a refusal, and undo whatever the call did, the way the route's missing commit would."""
    with pytest.raises(kind) as refusal:
        with db.begin_nested():
            call()
    return refusal.value


def booked(db, student: Student, monday: PickupDay, food: dict, *names: str, substitutes=()) -> Booking:
    """A student holds Monday's first free time and books these."""
    free = next(slot for slot in slots_of(db, monday) if slot.booked_count == 0 and not db.scalar(select(Hold).where(Hold.slot_id == slot.id)))
    rules.hold_slot(db, student, free.id, OPEN)
    return rules.book(db, student, [Choice(food[n].id) for n in names], [food[n].id for n in substitutes], OPEN)


# ---------- holding a time (S5, S8) ----------


def test_a_time_is_held_for_10_minutes(db, monday):
    student = make_student(db)
    first = slots_of(db, monday)[0]

    hold = rules.hold_slot(db, student, first.id, OPEN)

    assert (hold.slot_id, hold.held_until) == (first.id, OPEN + timedelta(minutes=10))


@pytest.mark.parametrize(
    "now, message",
    [
        (BEFORE_OPEN, "Booking for Monday, November 9 opens Sunday, November 8 at 5:00 p.m."),
        (CLOSED, "Booking for Monday, November 9 is over."),
    ],
)
def test_a_time_can_only_be_held_while_booking_is_open(db, monday, now, message):
    with pytest.raises(Problem) as refusal:
        rules.hold_slot(db, make_student(db), slots_of(db, monday)[0].id, now)
    assert refusal.value.message == message


def test_a_closed_day_says_why(db, monday):
    monday.closed_at, monday.closed_reason = OPEN, "snow storm"

    with pytest.raises(Problem, match="Monday, November 9 is closed: snow storm"):
        rules.hold_slot(db, make_student(db), slots_of(db, monday)[0].id, OPEN)


def test_one_hold_at_a_time(db, monday):
    """Holding a second time lets go of the first, so nobody can block several at 5 pm."""
    student = make_student(db)
    first, second = slots_of(db, monday)[:2]
    rules.hold_slot(db, student, first.id, OPEN)

    rules.hold_slot(db, student, second.id, OPEN + timedelta(minutes=1))

    assert db.scalars(select(Hold.slot_id).where(Hold.student_id == student.id)).all() == [second.id]


def test_holding_the_same_time_again_adds_no_time(db, monday):
    student = make_student(db)
    first = slots_of(db, monday)[0]
    rules.hold_slot(db, student, first.id, OPEN)

    hold = rules.hold_slot(db, student, first.id, OPEN + timedelta(minutes=9))

    assert hold.held_until == OPEN + timedelta(minutes=10)


def test_a_held_time_is_not_offered_to_others_until_the_hold_runs_out(db, monday):
    first = slots_of(db, monday)[0]
    rules.hold_slot(db, make_student(db), first.id, OPEN)
    ben = make_student(db)

    with pytest.raises(TimeTaken, match="Someone else just took that time"):
        rules.hold_slot(db, ben, first.id, OPEN + timedelta(minutes=9))
    rules.hold_slot(db, ben, first.id, OPEN + timedelta(minutes=10))


def test_a_booked_time_is_full(db, monday, food):
    booking = booked(db, make_student(db), monday, food, "rice")

    with pytest.raises(TimeTaken):
        rules.hold_slot(db, make_student(db), booking.slot_id, OPEN)


# ---------- who may book (F1, F2, S6) ----------


def test_one_upcoming_booking_at_a_time(db, monday, food):
    """F2: a booking for Monday means no hold for Thursday."""
    student = make_student(db)
    booked(db, student, monday, food, "rice")
    thursday = make_pickup_day(db, date(2026, 11, 12))

    with pytest.raises(Problem, match="You already have a booking, for Monday, November 9"):
        rules.hold_slot(db, student, slots_of(db, thursday)[0].id, datetime(2026, 11, 11, 21, 0, tzinfo=UTC))


def test_after_cancelling_a_day_it_cannot_be_booked_again(db, monday, food):
    """S6: otherwise cancelling and booking again would change the items. A later day is fine."""
    student = make_student(db)
    booked(db, student, monday, food, "rice")
    rules.cancel(db, student, OPEN)

    with pytest.raises(Problem, match="You cancelled your booking for Monday, November 9, so it can't be booked again"):
        rules.hold_slot(db, student, slots_of(db, monday)[5].id, OPEN)
    thursday = make_pickup_day(db, date(2026, 11, 12))
    rules.hold_slot(db, student, slots_of(db, thursday)[0].id, datetime(2026, 11, 11, 21, 0, tzinfo=UTC))


@pytest.mark.parametrize(
    "last_pickup, allowed",
    [
        (date(2026, 10, 12), True),  # 28 days before Monday 9 November
        (date(2026, 10, 13), False),  # 27 days
    ],
)
def test_the_pickup_gap_counts_calendar_days(db, monday, last_pickup, allowed):
    """F1: 28 days, from the date of the last pickup to the date of the new one."""
    student = make_student(db)
    student.last_pickup_on = last_pickup

    if allowed:
        rules.hold_slot(db, student, slots_of(db, monday)[0].id, OPEN)
    else:
        with pytest.raises(Problem, match="Your next pickup can be on Tuesday, November 10 or later."):
            rules.hold_slot(db, student, slots_of(db, monday)[0].id, OPEN)


@pytest.mark.parametrize("no_shows_count", [False, True])
def test_no_shows_count_toward_the_gap_only_if_the_setting_says_so(db, monday, no_shows_count):
    db.get(Settings, 1).no_shows_count = no_shows_count
    student = make_student(db)
    last_monday = make_pickup_day(db, MONDAY - timedelta(days=7))
    add(
        db,
        Booking(
            student_id=student.id,
            pickup_day_id=last_monday.id,
            slot_id=slots_of(db, last_monday)[0].id,
            code="N2S",
            status="no_show",
            no_show_at=OPEN - timedelta(days=7),
        ),
    )
    settings = db.get(Settings, 1)

    allowed_on = rules.next_pickup_allowed_on(db, student, settings)

    assert allowed_on == (MONDAY + timedelta(days=21) if no_shows_count else None)


# ---------- pressing Book ----------


def test_booking_takes_the_place_and_the_food(db, monday, food):
    student = make_student(db)
    first = slots_of(db, monday)[0]
    rules.hold_slot(db, student, first.id, OPEN)

    booking = rules.book(
        db,
        student,
        [Choice(food["quick oats"].id), Choice(food["chicken"].id)],
        [food["rice"].id, food["steel-cut oats"].id],
        OPEN + timedelta(minutes=4),
    )

    assert re.fullmatch(r"[A-Z][2-9][A-Z]", booking.code)
    assert (booking.status, booking.slot_id, booking.booked_at) == ("booked", first.id, OPEN + timedelta(minutes=4))
    assert first.booked_count == 1
    assert (food["quick oats"].stock, food["chicken"].stock, food["rice"].stock) == (4, 1, 5)  # substitutes aren't reserved (U3)
    assert db.get(Hold, student.id) is None
    ranked = db.scalars(
        select(BookingSubstitute.variety_id).where(BookingSubstitute.booking_id == booking.id).order_by(BookingSubstitute.rank)
    ).all()
    assert ranked == [food["rice"].id, food["steel-cut oats"].id]


def test_booking_needs_a_hold(db, monday, food):
    with pytest.raises(Problem, match="Choose a pickup time first."):
        rules.book(db, make_student(db), [Choice(food["rice"].id)], [], OPEN)


def test_a_hold_that_ran_out_cannot_be_booked(db, monday, food):
    student = make_student(db)
    rules.hold_slot(db, student, slots_of(db, monday)[0].id, OPEN)

    refusal = refused(db, Problem, lambda: rules.book(db, student, [Choice(food["rice"].id)], [], OPEN + timedelta(minutes=10)))

    assert refusal.message == "Your 10 minutes ran out, so the time was let go. Choose a time again."
    assert food["rice"].stock == 5


def test_pressing_book_twice_makes_one_booking(db, monday, food):
    """B4: the second press finds the first booking, and says its code."""
    student = make_student(db)
    first = booked(db, student, monday, food, "rice")

    with pytest.raises(AlreadyBooked, match=f"Your code is {first.code}"):
        rules.book(db, student, [Choice(food["rice"].id)], [], OPEN)
    assert db.scalar(select(func.count()).select_from(Booking)) == 1


@pytest.mark.parametrize(
    "items, substitutes, message",
    [
        ([], [], "Choose at least one thing."),
        (["rice", "rice"], [], "Each kind of food can be listed once."),
        (["quick oats", "steel-cut oats"], [], "You can choose 1 Oats at most, counting all its kinds together."),
        (["bread"], [], "Bread is an extra: ask for it at pickup instead."),
        (["rice"], ["rice"], "A substitute can't be something already on your list."),
        (["rice"], ["chicken", "chicken"], "Each substitute can be listed once."),
        (["rice"], ["bread"], "Bread is an extra: ask for it at pickup instead."),
    ],
)
def test_the_food_rules(db, monday, food, items, substitutes, message):
    """I3, E1, U2: checked by the code, because they need the settings or other tables."""
    student = make_student(db)
    rules.hold_slot(db, student, slots_of(db, monday)[0].id, OPEN)

    refusal = refused(
        db, Problem, lambda: rules.book(db, student, [Choice(food[n].id) for n in items], [food[n].id for n in substitutes], OPEN)
    )

    assert refusal.message == message


def test_the_item_limit_and_the_substitute_limit(db, monday, food):
    settings = db.get(Settings, 1)
    settings.item_limit, settings.substitute_limit = 2, 1
    student = make_student(db)
    rules.hold_slot(db, student, slots_of(db, monday)[0].id, OPEN)
    three = [Choice(food[n].id) for n in ["quick oats", "chicken", "rice"]]

    assert refused(db, Problem, lambda: rules.book(db, student, three, [], OPEN)).message == (
        "You can choose up to 2 things. Your list has 3."
    )
    two_substitutes = [food["steel-cut oats"].id, food["rice"].id]
    assert refused(db, Problem, lambda: rules.book(db, student, three[:1], two_substitutes, OPEN)).message == (
        "You can list up to 1 substitutes."
    )


def test_hidden_food_cannot_be_booked(db, monday, food):
    food["rice"].active = False
    student = make_student(db)
    rules.hold_slot(db, student, slots_of(db, monday)[0].id, OPEN)

    refusal = refused(db, Problem, lambda: rules.book(db, student, [Choice(food["rice"].id)], [], OPEN))

    assert refusal.message == "White rice isn't on the list any more. Choose something else."


def test_food_that_ran_out_while_choosing(db, monday, food):
    """The whole booking is undone: the place and the other food are untouched (I4)."""
    student = make_student(db)
    first = slots_of(db, monday)[0]
    rules.hold_slot(db, student, first.id, OPEN)
    food["chicken"].stock = 0

    refusal = refused(
        db, TimeTaken, lambda: rules.book(db, student, [Choice(food["rice"].id), Choice(food["chicken"].id)], [], OPEN)
    )

    assert refusal.message == "Sorry, Chunk chicken has just run out. Choose something else."
    assert (first.booked_count, food["rice"].stock) == (0, 5)
    assert db.get(Hold, student.id) is not None  # still theirs, to choose again


# ---------- cancelling (S6, I6) ----------


def test_cancelling_gives_back_the_place_and_the_food(db, monday, food):
    student = make_student(db)
    booking = booked(db, student, monday, food, "quick oats", "chicken")
    slot = db.get(Slot, booking.slot_id)

    rules.cancel(db, student, OPEN + timedelta(hours=1))

    assert (booking.status, booking.cancel_reason, booking.cancelled_at) == ("cancelled", "student", OPEN + timedelta(hours=1))
    assert (slot.booked_count, food["quick oats"].stock, food["chicken"].stock) == (0, 5, 2)
    # Someone else can have the time straight away.
    rules.hold_slot(db, make_student(db), slot.id, OPEN + timedelta(hours=1))


def test_cancelling_closes_when_booking_closes(db, monday, food):
    student = make_student(db)
    booked(db, student, monday, food, "rice")

    with pytest.raises(Problem, match="Cancelling closed at Monday, November 9 at 12:00 p.m."):
        rules.cancel(db, student, CLOSED)


def test_nothing_to_cancel(db, monday):
    with pytest.raises(NotFound):
        rules.cancel(db, make_student(db), OPEN)


# ---------- at the same moment, on two connections ----------


@pytest.fixture
def world(engine):
    """Committed rows for the race tests: the settings, Monday with two 1-place slots,
    two students, and one tin of chicken. Everything is deleted afterwards."""
    with Session(engine) as db:
        db.add(Settings(**SAMPLE_SETTINGS))
        staff = Staff(username="Race staff", role="volunteer")
        db.add(staff)
        db.flush()
        day = PickupDay(
            pickup_date=MONDAY + timedelta(days=900),
            booking_opens_at=OPEN - timedelta(hours=1),
            booking_closes_at=OPEN + timedelta(hours=18),
            pickup_starts_at=OPEN + timedelta(hours=21),
            pickup_ends_at=OPEN + timedelta(hours=23),
            no_show_at=OPEN + timedelta(hours=24),
        )
        db.add(day)
        db.flush()
        slots = [Slot(pickup_day_id=day.id, starts_at=OPEN + timedelta(days=1, minutes=10 * n), capacity=1) for n in range(2)]
        ana = Student(id_hash="a" * 64, created_by_staff_id=staff.id)
        ben = Student(id_hash="b" * 64, created_by_staff_id=staff.id)
        category = Category(name="Race category")
        db.add_all([*slots, ana, ben, category])
        db.flush()
        item = Item(name="Race item", category_id=category.id)
        db.add(item)
        db.flush()
        tin = Variety(item_id=item.id, name="Last tin", stock=1)
        db.add(tin)
        db.commit()
        ids = {
            "day": day.id,
            "slots": [slot.id for slot in slots],
            "ana": ana.id,
            "ben": ben.id,
            "tin": tin.id,
            "item": item.id,
            "category": category.id,
            "staff": staff.id,
        }
    yield ids
    with engine.begin() as tidy:
        tidy.execute(delete(Booking).where(Booking.pickup_day_id == ids["day"]))
        tidy.execute(delete(Hold).where(Hold.student_id.in_([ids["ana"], ids["ben"]])))
        tidy.execute(delete(Slot).where(Slot.pickup_day_id == ids["day"]))
        tidy.execute(delete(PickupDay).where(PickupDay.id == ids["day"]))
        tidy.execute(delete(Variety).where(Variety.id == ids["tin"]))
        tidy.execute(delete(Item).where(Item.id == ids["item"]))
        tidy.execute(delete(Category).where(Category.id == ids["category"]))
        tidy.execute(delete(Student).where(Student.id.in_([ids["ana"], ids["ben"]])))
        tidy.execute(delete(Staff).where(Staff.id == ids["staff"]))
        tidy.execute(delete(Settings))


def at_the_same_moment(engine, first, second) -> dict:
    """Run first() and, while its transaction is still open, second() on another connection.

    Each gets its own session. first() runs, then waits; second() starts and
    blocks on a lock; then first commits, and second finishes. Returns what
    each one raised, if anything.
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


def test_two_students_hold_the_last_place_at_the_same_moment(engine, world):
    slot = world["slots"][0]

    results = at_the_same_moment(
        engine,
        lambda db: rules.hold_slot(db, db.get(Student, world["ana"]), slot, OPEN),
        lambda db: rules.hold_slot(db, db.get(Student, world["ben"]), slot, OPEN),
    )

    assert isinstance(results["second"], TimeTaken)
    with Session(engine) as db:
        assert db.scalars(select(Hold.student_id).where(Hold.slot_id == slot)).all() == [world["ana"]]


def test_two_students_book_the_last_tin_at_the_same_moment(engine, world):
    """Each holds their own time. Only one may get the tin (I4)."""
    with Session(engine) as db:
        rules.hold_slot(db, db.get(Student, world["ana"]), world["slots"][0], OPEN)
        rules.hold_slot(db, db.get(Student, world["ben"]), world["slots"][1], OPEN)
        db.commit()
    tin = [Choice(world["tin"])]

    results = at_the_same_moment(
        engine,
        lambda db: rules.book(db, db.get(Student, world["ana"]), tin, [], OPEN),
        lambda db: rules.book(db, db.get(Student, world["ben"]), tin, [], OPEN),
    )

    assert isinstance(results["second"], TimeTaken)
    assert "Last tin has just run out" in results["second"].message
    with engine.connect() as check:
        assert check.execute(select(Variety.stock).where(Variety.id == world["tin"])).scalar_one() == 0
        assert check.execute(select(func.count()).select_from(Booking).where(Booking.pickup_day_id == world["day"])).scalar_one() == 1


def test_pressing_book_twice_at_the_same_moment(engine, world):
    """B4: a double click sends two requests. The second waits, then finds the booking."""
    with Session(engine) as db:
        rules.hold_slot(db, db.get(Student, world["ana"]), world["slots"][0], OPEN)
        db.commit()
    tin = [Choice(world["tin"])]

    results = at_the_same_moment(
        engine,
        lambda db: rules.book(db, db.get(Student, world["ana"]), tin, [], OPEN),
        lambda db: rules.book(db, db.get(Student, world["ana"]), tin, [], OPEN),
    )

    assert isinstance(results["second"], AlreadyBooked)
    with engine.connect() as check:
        assert check.execute(select(func.count()).select_from(Booking).where(Booking.pickup_day_id == world["day"])).scalar_one() == 1


# ---------- food with no number (decided 12 Nov) ----------


def test_food_with_no_number_can_be_booked_by_anyone_and_keeps_no_number(db, monday, food):
    """Nobody counts the rice, so every student can book it. Nothing is taken off or put back."""
    food["rice"].stock = None
    first = booked(db, make_student(db), monday, food, "rice")
    booked(db, make_student(db), monday, food, "rice")
    assert food["rice"].stock is None

    rules.cancel(db, db.get(Student, first.student_id), OPEN + timedelta(hours=1))

    assert food["rice"].stock is None
