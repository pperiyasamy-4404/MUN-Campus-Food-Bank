"""Closing a day (S7), opening it again, and moving its booking times (S9),
straight from app/services/day_changes.py.

The pickup day is Monday 9 November 2026: booking opens Sunday at 5 pm and
closes Monday at 12 pm, pickup is 3:30 to 5:30 pm and no-shows are at 6 pm,
St. John's time (UTC-3:30 in November). The web side is in test_days_api.py.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Booking, PickupDay, Slot, Staff, Student, Variety
from app.problems import NotFound, Problem
from app.services import booking as booking_rules
from app.services import day_changes, no_shows
from app.services.booking import Choice
from app.services.day_changes import AlreadyClosed
from app.services.pickup_days import make_days_ahead, make_pickup_day
from app.services.settings import food_bank_settings
from tests.helpers import THURSDAY, coordinator, make_student
from tests.test_booking import at_the_same_moment, world  # noqa: F401 (world is a fixture)
from tests.test_booking import OPEN as WORLD_OPEN
from tests.test_no_shows import OPEN, PACKING, booked, food, monday, packed, refused, stock  # noqa: F401

SUNDAY_4PM = datetime(2026, 11, 8, 19, 30, tzinfo=UTC)
MONDAY_1PM = datetime(2026, 11, 9, 16, 30, tzinfo=UTC)
NO_SHOW = datetime(2026, 11, 9, 21, 30, tzinfo=UTC)  # Monday 6:00 pm
MONDAY = date(2026, 11, 9)


@pytest.fixture
def alex(db_with_sample_week) -> Staff:
    return coordinator(db_with_sample_week)


# ---------- closing a day (S7) ----------


def test_closing_a_day_cancels_every_booking_and_puts_the_food_back(db, monday, food, alex):
    ana, ben = make_student(db), make_student(db)
    booked(db, monday, ana, food, "quick oats", "rice")
    # Ben's bag is packed: no sunflower oil on the shelf, so lentils went in instead.
    packed(
        db, monday, ben, food, "quick oats", "sunflower oil",
        missing=["sunflower oil"], substitutes=["lentils"], uses=["lentils"],
    )
    assert stock(food) == {"quick oats": 3, "sunflower oil": 0, "rice": 4, "lentils": 4, "white bread": 5}

    closed = day_changes.close_day(db, MONDAY, "Snow storm", alex, MONDAY_1PM)

    assert (closed.cancelled, closed.were_packed) == (2, 1)
    assert (monday.closed_at, monday.closed_reason) == (MONDAY_1PM, "Snow storm")
    bookings = db.scalars(select(Booking).where(Booking.pickup_day_id == monday.id)).all()
    assert {(b.status, b.cancel_reason, b.cancelled_at) for b in bookings} == {("cancelled", "day_closed", MONDAY_1PM)}
    # What was really in each bag goes back. The sunflower oil was never on the shelf, so it stays at 0.
    assert stock(food) == {"quick oats": 5, "sunflower oil": 0, "rice": 5, "lentils": 5, "white bread": 5}
    assert db.scalar(select(func.sum(Slot.booked_count)).where(Slot.pickup_day_id == monday.id)) == 0


def test_closing_is_logged_with_who_and_which_day(db, monday, alex):
    day_changes.close_day(db, MONDAY, "Snow storm", alex, SUNDAY_4PM)

    line = db.scalar(select(AuditLog).where(AuditLog.action == "closed_day"))
    assert (line.staff_id, line.pickup_day_id, line.at) == (alex.id, monday.id, SUNDAY_4PM)


def test_bags_already_handed_over_stay_handed_over(db, monday, food, alex):
    bag = packed(db, monday, make_student(db), food, "quick oats")
    bag.status, bag.picked_up_at, bag.picked_up_by_staff_id = "picked_up", MONDAY_1PM, alex.id
    db.flush()

    closed = day_changes.close_day(db, MONDAY, "Burst pipe", alex, MONDAY_1PM + timedelta(minutes=5))

    assert closed.cancelled == 0
    assert bag.status == "picked_up"
    assert food["quick oats"].stock == 4


def test_nobody_can_hold_or_book_a_closed_day(db, monday, food, alex):
    ana = make_student(db)
    slot = db.scalars(select(Slot).where(Slot.pickup_day_id == monday.id)).first()
    day_changes.close_day(db, MONDAY, "Snow storm", alex, SUNDAY_4PM)

    refusal = refused(db, Problem, lambda: booking_rules.hold_slot(db, ana, slot.id, OPEN))

    assert refusal.message == "Monday, November 9 is closed: Snow storm"


def test_students_whose_day_was_closed_can_book_another_day(db, monday, food, alex):
    """F3: a cancellation never counts toward the pickup gap."""
    ana = make_student(db)
    booked(db, monday, ana, food, "quick oats")
    thursday = make_pickup_day(db, THURSDAY)
    day_changes.close_day(db, MONDAY, "Snow storm", alex, MONDAY_1PM)

    wednesday_6pm = datetime(2026, 11, 11, 21, 30, tzinfo=UTC)
    assert booking_rules.why_not(db, ana, thursday, food_bank_settings(db), wednesday_6pm) is None


def test_a_closed_day_has_no_no_shows(db, monday, food, alex):
    booked(db, monday, make_student(db), food, "quick oats")
    day_changes.close_day(db, MONDAY, "Snow storm", alex, MONDAY_1PM)

    assert no_shows.due_no_shows(db, NO_SHOW) == []


def test_the_reason_is_tidied_and_has_to_be_there(db, monday, alex):
    for empty in ["", "   "]:
        refusal = refused(db, Problem, lambda: day_changes.close_day(db, MONDAY, empty, alex, SUNDAY_4PM))
        assert refusal.message == "Say why it's closed. Students see the reason."
    refusal = refused(db, Problem, lambda: day_changes.close_day(db, MONDAY, "x" * 201, alex, SUNDAY_4PM))
    assert refusal.message == "Keep the reason to 200 characters. Students see it."

    day_changes.close_day(db, MONDAY, "  Snow \n storm ", alex, SUNDAY_4PM)

    assert monday.closed_reason == "Snow storm"


def test_a_day_is_closed_once(db, monday, alex):
    day_changes.close_day(db, MONDAY, "Snow storm", alex, SUNDAY_4PM)

    refusal = refused(db, AlreadyClosed, lambda: day_changes.close_day(db, MONDAY, "Again", alex, SUNDAY_4PM))

    assert refusal.message == "Monday, November 9 is closed already."
    assert monday.closed_reason == "Snow storm"


def test_a_day_that_is_over_cant_be_closed(db, monday, alex):
    refusal = refused(db, Problem, lambda: day_changes.close_day(db, MONDAY, "Snow storm", alex, NO_SHOW))

    assert refusal.message == "Monday, November 9 is over, so it can't be closed."


# ---------- closing a date further ahead ----------


def test_a_date_further_ahead_is_made_then_closed(db_with_sample_week, alex):
    db = db_with_sample_week
    christmas_monday = date(2026, 12, 21)

    day_changes.close_day(db, christmas_monday, "Christmas break", alex, SUNDAY_4PM)

    day = db.scalar(select(PickupDay).where(PickupDay.pickup_date == christmas_monday))
    assert day.closed_reason == "Christmas break"
    assert db.scalar(select(func.count()).select_from(Slot).where(Slot.pickup_day_id == day.id)) == 12


def test_the_jobs_never_open_a_day_closed_ahead(db_with_sample_week, alex):
    db = db_with_sample_week
    christmas_monday = date(2026, 12, 21)
    day_changes.close_day(db, christmas_monday, "Christmas break", alex, SUNDAY_4PM)

    # Tuesday 15 December: the next week includes Monday 21.
    make_days_ahead(db, datetime(2026, 12, 15, 12, 0, tzinfo=UTC))

    days = db.scalars(select(PickupDay).where(PickupDay.pickup_date == christmas_monday)).all()
    assert [day.closed_reason for day in days] == ["Christmas break"]


def test_only_pickup_days_in_the_next_year_can_be_closed(db_with_sample_week, alex):
    db = db_with_sample_week
    tuesday, today, far = date(2026, 11, 17), date(2026, 11, 8), date(2027, 11, 15)

    assert refused(db, Problem, lambda: day_changes.close_day(db, tuesday, "x", alex, SUNDAY_4PM)).message == (
        "Tuesday, November 17 isn't a pickup day, so there's nothing to close."
    )
    assert refused(db, NotFound, lambda: day_changes.close_day(db, today, "x", alex, SUNDAY_4PM)).message == (
        "There's no pickup on Sunday, November 8."
    )
    assert refused(db, Problem, lambda: day_changes.close_day(db, far, "x", alex, SUNDAY_4PM)).message == (
        "Dates can be closed up to a year ahead."
    )
    assert db.scalar(select(func.count()).select_from(PickupDay)) == 0


# ---------- opening it again ----------


def test_a_day_closed_before_anyone_booked_can_be_opened_again(db, monday, alex):
    day_changes.close_day(db, MONDAY, "Oops, wrong day", alex, SUNDAY_4PM - timedelta(hours=1))

    day_changes.reopen_day(db, MONDAY, alex, SUNDAY_4PM)

    assert (monday.closed_at, monday.closed_reason) == (None, None)
    line = db.scalar(select(AuditLog).where(AuditLog.action == "reopened_day"))
    assert (line.staff_id, line.pickup_day_id) == (alex.id, monday.id)


def test_a_day_whose_closing_cancelled_bookings_stays_closed(db, monday, food, alex):
    booked(db, monday, make_student(db), food, "quick oats")
    day_changes.close_day(db, MONDAY, "Snow storm", alex, MONDAY_1PM)

    refusal = refused(db, Problem, lambda: day_changes.reopen_day(db, MONDAY, alex, MONDAY_1PM))

    assert refusal.message == (
        "Closing Monday, November 9 cancelled 1 booking, so it stays closed: those students couldn't book it again."
    )
    assert monday.closed_reason == "Snow storm"


def test_only_a_closed_day_that_isnt_over_can_be_opened_again(db, monday, alex):
    refusal = refused(db, Problem, lambda: day_changes.reopen_day(db, MONDAY, alex, SUNDAY_4PM))
    assert refusal.message == "Monday, November 9 isn't closed."

    day_changes.close_day(db, MONDAY, "Snow storm", alex, SUNDAY_4PM)
    refusal = refused(db, Problem, lambda: day_changes.reopen_day(db, MONDAY, alex, NO_SHOW))
    assert refusal.message == "Monday, November 9 is over."


# ---------- moving one day's booking times (S9) ----------

SUNDAY_7PM = datetime(2026, 11, 8, 22, 30, tzinfo=UTC)
MONDAY_11AM = datetime(2026, 11, 9, 14, 30, tzinfo=UTC)


def test_one_days_booking_times_move_and_no_other_days(db, monday, alex):
    thursday = make_pickup_day(db, THURSDAY)
    thursday_times = (thursday.booking_opens_at, thursday.booking_closes_at)

    day_changes.move_booking_times(db, MONDAY, SUNDAY_7PM, MONDAY_11AM, alex, SUNDAY_4PM)

    assert (monday.booking_opens_at, monday.booking_closes_at) == (SUNDAY_7PM, MONDAY_11AM)
    assert (thursday.booking_opens_at, thursday.booking_closes_at) == thursday_times
    # The settings stay as they were: 5 pm the day before, until 12 pm.
    assert food_bank_settings(db).booking_opens_time.hour == 17
    line = db.scalar(select(AuditLog).where(AuditLog.action == "moved_booking_times"))
    assert (line.staff_id, line.pickup_day_id) == (alex.id, monday.id)


def test_booking_times_have_to_make_sense(db, monday, alex):
    def move(opens_at, closes_at, now=SUNDAY_4PM):
        return refused(db, Problem, lambda: day_changes.move_booking_times(db, MONDAY, opens_at, closes_at, alex, now)).message

    assert move(MONDAY_11AM, SUNDAY_7PM) == "Booking has to open before it closes."
    assert move(SUNDAY_7PM, SUNDAY_4PM - timedelta(minutes=1)) == "Booking has to open before it closes."
    assert move(SUNDAY_4PM - timedelta(hours=2), SUNDAY_4PM - timedelta(minutes=1)) == (
        "The new close time has passed already. Choose a later one."
    )
    assert move(SUNDAY_7PM, monday.pickup_starts_at + timedelta(minutes=1)) == (
        "Booking has to close by the time pickup starts, Monday, November 9 at 3:30 p.m., so the bags can be packed"
    )


def test_booking_times_move_only_until_booking_closes(db, monday, alex):
    message = refused(
        db, Problem, lambda: day_changes.move_booking_times(db, MONDAY, SUNDAY_7PM, MONDAY_1PM, alex, PACKING)
    ).message
    assert message == "Booking for Monday, November 9 is over, and packing has started."

    day_changes.close_day(db, MONDAY, "Snow storm", alex, SUNDAY_4PM)
    message = refused(
        db, Problem, lambda: day_changes.move_booking_times(db, MONDAY, SUNDAY_7PM, MONDAY_11AM, alex, SUNDAY_4PM)
    ).message
    assert message == "Monday, November 9 is closed."


# ---------- two people at the same moment ----------


def _tidy_log(engine, staff_id: int) -> None:
    with engine.begin() as tidy:
        tidy.execute(delete(AuditLog).where(AuditLog.staff_id == staff_id))


def test_closing_while_a_student_presses_book_closing_first(engine, world):  # noqa: F811
    """The day is closing, with its slots locked. Book waits, then finds the day closed."""
    with Session(engine) as db:
        booking_rules.hold_slot(db, db.get(Student, world["ana"]), world["slots"][0], WORLD_OPEN)
        day_date = db.get(PickupDay, world["day"]).pickup_date
        db.commit()
    try:
        results = at_the_same_moment(
            engine,
            lambda db: day_changes.close_day(db, day_date, "Snow storm", db.get(Staff, world["staff"]), WORLD_OPEN),
            lambda db: booking_rules.book(db, db.get(Student, world["ana"]), [Choice(world["tin"])], [], WORLD_OPEN),
        )

        assert isinstance(results["second"], Problem)
        assert results["second"].message.endswith("is closed: Snow storm")
        with engine.connect() as check:
            assert check.execute(select(func.count()).select_from(Booking).where(Booking.pickup_day_id == world["day"])).scalar_one() == 0
            assert check.execute(select(Variety.stock).where(Variety.id == world["tin"])).scalar_one() == 1
    finally:
        _tidy_log(engine, world["staff"])


def test_closing_while_a_student_presses_book_booking_first(engine, world):  # noqa: F811
    """The booking is saved first. Closing waits for it, then cancels it with the others."""
    with Session(engine) as db:
        booking_rules.hold_slot(db, db.get(Student, world["ana"]), world["slots"][0], WORLD_OPEN)
        day_date = db.get(PickupDay, world["day"]).pickup_date
        db.commit()
    try:
        results = at_the_same_moment(
            engine,
            lambda db: booking_rules.book(db, db.get(Student, world["ana"]), [Choice(world["tin"])], [], WORLD_OPEN),
            lambda db: day_changes.close_day(db, day_date, "Snow storm", db.get(Staff, world["staff"]), WORLD_OPEN),
        )

        assert results["second"] == "done"
        with engine.connect() as check:
            statuses = check.execute(select(Booking.status, Booking.cancel_reason).where(Booking.pickup_day_id == world["day"])).all()
            assert statuses == [("cancelled", "day_closed")]
            assert check.execute(select(Variety.stock).where(Variety.id == world["tin"])).scalar_one() == 1
            assert check.execute(select(Slot.booked_count).where(Slot.id == world["slots"][0])).scalar_one() == 0
    finally:
        _tidy_log(engine, world["staff"])
