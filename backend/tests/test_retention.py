"""Deleting what we promised not to keep (P7, P13), and tidying up, straight from
app/services/retention.py and app/services/totals.py.

With the sample settings, booking details are kept for 90 days after the pickup
day. Monday 9 November 2026's are deleted on Monday 8 February 2027.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import (
    AuditLog,
    Booking,
    BookingItem,
    BookingSubstitute,
    Category,
    CounterItem,
    Hold,
    Item,
    LoginFailure,
    LoginSession,
    PickupDay,
    SetupCode,
    Student,
    Variety,
    WalkIn,
    WeeklyItemTotal,
    WeeklyTotal,
)
from app.services import retention, totals
from tests.helpers import MONDAY, THURSDAY, add, make_day, make_slot, make_staff, make_student, new_hash

PICKUP = datetime(2026, 11, 9, 19, 10, tzinfo=UTC)  # Monday 3:40 pm
LAST_DAY_KEPT = datetime(2027, 2, 8, 3, 29, tzinfo=UTC)  # Sunday 7 February 2027, 11:59 pm in St. John's
FIRST_DAY_GONE = datetime(2027, 2, 8, 3, 30, tzinfo=UTC)  # Monday 8 February 2027, midnight in St. John's


# ---------- the world ----------


@pytest.fixture
def food(db_with_settings) -> dict[str, Variety]:
    db = db_with_settings
    pantry = add(db, Category(name="Pantry"))

    def variety(item_name: str, name: str, is_extra: bool = False) -> Variety:
        item = add(db, Item(name=item_name, category_id=pantry.id, is_extra=is_extra))
        return add(db, Variety(item_id=item.id, name=name, stock=5))

    return {
        "quick oats": variety("Oats", "Quick oats"),
        "sunflower oil": variety("Cooking oil", "Sunflower oil"),
        "rice": variety("Rice", "White rice"),
        "lentils": variety("Lentils", "Red lentils"),
        "white bread": variety("Bread", "White bread", is_extra=True),
    }


def a_bag(
    db, day: PickupDay, status: str, food: dict[str, Variety], *names: str, code: str, missing: dict[str, int] | None = None
) -> Booking:
    """A booking on this day, already in the state given, with this food booked.

    missing says how many weren't on the shelf when it was packed, like {"sunflower oil": 1}.
    """
    staff = make_staff(db)
    times = {
        "picked_up": {"packed_at": PICKUP, "packed_by_staff_id": staff.id, "picked_up_at": PICKUP, "picked_up_by_staff_id": staff.id},
        "no_show": {"no_show_at": PICKUP + timedelta(hours=2)},
        "cancelled": {"cancelled_at": PICKUP - timedelta(days=1), "cancel_reason": "student"},
    }[status]
    slot = make_slot(db, day, minutes_in=10 * db.scalar(select(func.count()).select_from(Booking).where(Booking.pickup_day_id == day.id)))
    booking = add(
        db,
        Booking(student_id=make_student(db).id, pickup_day_id=day.id, slot_id=slot.id, code=code, status=status, **times),
    )
    for name in names:
        add(db, BookingItem(booking_id=booking.id, variety_id=food[name].id, missing=(missing or {}).get(name, 0)))
    return booking


def given_at_counter(db, variety: Variety, quantity: int = 1, booking: Booking | None = None, walk_in: WalkIn | None = None):
    item = db.get(Item, variety.item_id)
    return add(
        db,
        CounterItem(
            booking_id=booking.id if booking else None,
            walk_in_id=walk_in.id if walk_in else None,
            variety_id=variety.id,
            item_id=item.id,
            is_extra=item.is_extra,
            quantity=quantity,
        ),
    )


def a_walk_in(db, day: PickupDay) -> WalkIn:
    return add(db, WalkIn(student_id=make_student(db).id, pickup_day_id=day.id, served_at=PICKUP, served_by_staff_id=make_staff(db).id))


def week_items(db, week: date) -> dict[int, int]:
    rows = db.execute(select(WeeklyItemTotal.item_id, WeeklyItemTotal.given_out).where(WeeklyItemTotal.week_starts_on == week))
    return dict(rows.all())


def how_many(db, table) -> int:
    return db.scalar(select(func.count()).select_from(table))


# ---------- booking details, after the retention period (P7) ----------


@pytest.mark.parametrize("now, deleted", [(LAST_DAY_KEPT, False), (FIRST_DAY_GONE, True)])
def test_details_are_kept_for_90_days_then_deleted(db, food, now, deleted):
    monday = make_day(db, MONDAY)
    a_bag(db, monday, "picked_up", food, "quick oats", code="A2B")

    assert retention.days_past_retention(db, now) == ([monday.id] if deleted else [])


def test_a_days_totals_are_saved_then_its_details_deleted(db, food):
    """A bag handed over with bread from the counter. Its oil wasn't on the shelf,
    so lentils went in instead. A no-show, a cancelled booking, and a walk-in who took 2 rice."""
    monday = make_day(db, MONDAY)
    picked_up = a_bag(db, monday, "picked_up", food, "quick oats", "sunflower oil", code="A2B", missing={"sunflower oil": 1})
    add(db, BookingSubstitute(booking_id=picked_up.id, rank=1, variety_id=food["lentils"].id, replaces_variety_id=food["sunflower oil"].id))
    given_at_counter(db, food["white bread"], booking=picked_up)
    a_bag(db, monday, "no_show", food, "rice", code="C3D")
    a_bag(db, monday, "cancelled", food, "rice", code="E4F")
    given_at_counter(db, food["rice"], 2, walk_in=a_walk_in(db, monday))

    retention.save_totals_and_delete(db, monday.id)

    week = db.get(WeeklyTotal, MONDAY)
    assert (week.picked_up, week.walk_ins, week.no_shows, week.cancelled) == (1, 1, 1, 1)
    # The oil never went out, the lentils did. Nothing for the no-show or the cancelled booking.
    assert week_items(db, MONDAY) == {
        food["quick oats"].item_id: 1,
        food["lentils"].item_id: 1,
        food["white bread"].item_id: 1,
        food["rice"].item_id: 2,
    }
    for table in [Booking, BookingItem, BookingSubstitute, CounterItem, WalkIn]:
        assert how_many(db, table) == 0, table.__tablename__
    # The pickup day itself stays: it says nothing about anyone.
    assert db.get(PickupDay, monday.id) is not None


def test_two_days_in_one_week_add_up(db, food):
    for day, code in [(make_day(db, MONDAY), "A2B"), (make_day(db, THURSDAY), "C3D")]:
        a_bag(db, day, "picked_up", food, "quick oats", code=code)
        retention.save_totals_and_delete(db, day.id)

    # Thursday 12 November is in the week that starts on Monday 9 November.
    assert db.get(WeeklyTotal, MONDAY).picked_up == 2
    assert week_items(db, MONDAY) == {food["quick oats"].item_id: 2}


def test_a_day_is_counted_once(db, food):
    """Two runs reaching the same day: the second finds nothing left to count."""
    monday = make_day(db, MONDAY)
    a_bag(db, monday, "picked_up", food, "quick oats", code="A2B")

    retention.save_totals_and_delete(db, monday.id)
    retention.save_totals_and_delete(db, monday.id)

    assert db.get(WeeklyTotal, MONDAY).picked_up == 1
    assert week_items(db, MONDAY) == {food["quick oats"].item_id: 1}
    assert retention.days_past_retention(db, FIRST_DAY_GONE) == []


def test_totals_can_be_worked_out_while_the_details_are_still_here(db, food):
    """What the coordinator's page will use for recent weeks (step 9)."""
    monday = make_day(db, MONDAY)
    a_bag(db, monday, "picked_up", food, "quick oats", "rice", code="A2B")
    a_bag(db, monday, "no_show", food, "rice", code="C3D")

    day = totals.day_totals(db, monday)

    assert (day.picked_up, day.walk_ins, day.no_shows, day.cancelled) == (1, 0, 1, 0)
    assert day.given_out == {food["quick oats"].item_id: 1, food["rice"].item_id: 1}
    assert totals.week_of(THURSDAY) == MONDAY


def test_the_activity_log_is_deleted_after_90_days(db_with_settings):
    db = db_with_settings
    now = FIRST_DAY_GONE
    staff = make_staff(db)
    old = add(db, AuditLog(at=now - timedelta(days=90, seconds=1), staff_id=staff.id, action="created_student"))
    recent = add(db, AuditLog(at=now - timedelta(days=89), staff_id=staff.id, action="created_student"))

    assert retention.delete_old_log(db, now) == 1

    assert db.scalars(select(AuditLog.id).where(AuditLog.id.in_([old.id, recent.id]))).all() == [recent.id]


# ---------- accounts with no pickup for a year (P13) ----------

A_YEAR_ON = datetime(2027, 11, 10, 16, 0, tzinfo=UTC)  # Wednesday 10 November 2027, 12:30 pm in St. John's


@pytest.mark.parametrize("last_pickup_on, deleted", [(date(2026, 11, 9), True), (date(2026, 11, 10), False)])
def test_an_account_with_no_pickup_for_a_year_is_deleted(db_with_settings, last_pickup_on, deleted):
    db = db_with_settings
    student = make_student(db)
    student.last_pickup_on = last_pickup_on

    assert (student.id in retention.quiet_accounts(db, A_YEAR_ON)) == deleted


@pytest.mark.parametrize(
    "created_at, deleted",
    [
        # 11:30 pm on Monday 9 November 2026 in St. John's, already the 10th in UTC.
        (datetime(2026, 11, 10, 2, 0, tzinfo=UTC), True),
        # 12:00 am on Tuesday 10 November 2026 in St. John's.
        (datetime(2026, 11, 10, 3, 30, tzinfo=UTC), False),
    ],
)
def test_an_account_that_never_had_a_pickup_counts_from_when_it_was_made(db_with_settings, created_at, deleted):
    db = db_with_settings
    student = add(db, Student(id_hash=new_hash(), created_at=created_at, created_by_staff_id=make_staff(db).id))

    assert (student.id in retention.quiet_accounts(db, A_YEAR_ON)) == deleted


def quiet_student(db) -> Student:
    student = make_student(db)
    student.last_pickup_on = date(2026, 1, 5)
    db.flush()
    return student


def test_a_quiet_account_is_deleted_with_its_logins_and_codes(db_with_settings):
    db = db_with_settings
    student = quiet_student(db)
    add(db, LoginSession(token_hash=new_hash(), student_id=student.id, expires_at=A_YEAR_ON + timedelta(days=3)))
    add(db, SetupCode(code_hash=new_hash(), student_id=student.id, issued_at=A_YEAR_ON - timedelta(days=30), expires_at=A_YEAR_ON - timedelta(days=23)))
    logged = add(db, AuditLog(at=A_YEAR_ON - timedelta(days=1), staff_id=make_staff(db).id, action="created_student", student_id=student.id))

    assert retention.delete_account(db, student.id, A_YEAR_ON) is True

    db.expire_all()
    assert db.get(Student, student.id) is None
    assert how_many(db, LoginSession) == how_many(db, SetupCode) == 0
    # The log line stays until its own 90 days are up, but no longer says who.
    assert db.get(AuditLog, logged.id).student_id is None


def test_an_account_with_a_booking_on_record_is_kept(db_with_settings):
    """Like a student who never picked up, booking for next week."""
    db = db_with_settings
    student = quiet_student(db)
    add(db, Booking(student_id=student.id, slot_id=(slot := make_slot(db)).id, pickup_day_id=slot.pickup_day_id, code="A2B"))

    assert student.id not in retention.quiet_accounts(db, A_YEAR_ON)


def test_an_account_with_a_walk_in_on_record_is_kept(db_with_settings):
    db = db_with_settings
    student = quiet_student(db)
    add(db, WalkIn(student_id=student.id, pickup_day_id=make_day(db).id, served_at=PICKUP, served_by_staff_id=make_staff(db).id))

    assert student.id not in retention.quiet_accounts(db, A_YEAR_ON)


@pytest.mark.parametrize("runs_out_in, kept", [(timedelta(days=2), True), (-timedelta(days=2), False)])
def test_an_account_with_a_setup_code_still_running_is_kept(db_with_settings, runs_out_in, kept):
    """A volunteer just gave them a new code: they're about to use the account."""
    db = db_with_settings
    student = quiet_student(db)
    add(db, SetupCode(code_hash=new_hash(), student_id=student.id, issued_at=A_YEAR_ON - timedelta(days=5), expires_at=A_YEAR_ON + runs_out_in))

    assert (student.id not in retention.quiet_accounts(db, A_YEAR_ON)) == kept


def test_an_account_is_checked_again_once_it_is_locked(db_with_settings):
    """The student booked between the list being made and their turn to be deleted."""
    db = db_with_settings
    student = quiet_student(db)
    assert student.id in retention.quiet_accounts(db, A_YEAR_ON)
    add(db, Booking(student_id=student.id, slot_id=(slot := make_slot(db)).id, pickup_day_id=slot.pickup_day_id, code="A2B"))

    assert retention.delete_account(db, student.id, A_YEAR_ON) is False
    assert db.get(Student, student.id) is not None


# ---------- tidying up ----------

TIDY_AT = datetime(2026, 11, 9, 21, 45, tzinfo=UTC)  # Monday 6:15 pm, after the no-show time


def test_tidying_up_deletes_what_ran_out_and_keeps_the_rest(db_with_settings):
    db = db_with_settings
    student = make_student(db)
    for ends in [TIDY_AT, TIDY_AT + timedelta(minutes=1)]:
        add(db, LoginSession(token_hash=new_hash(), student_id=make_student(db).id, expires_at=ends))
        add(db, SetupCode(code_hash=new_hash(), student_id=make_student(db).id, issued_at=ends - timedelta(days=7), expires_at=ends))
    # Only tries in the last 15 minutes are counted (P9).
    for minutes_ago in [15, 14]:
        add(db, LoginFailure(who_hash=new_hash(), failed_at=TIDY_AT - timedelta(minutes=minutes_ago)))
    # Monday's pickup is over. Thursday's isn't, even though this hold ran out.
    add(db, Hold(student_id=student.id, slot_id=make_slot(db, make_day(db, MONDAY)).id, held_until=TIDY_AT - timedelta(days=1)))
    later = add(db, Hold(student_id=make_student(db).id, slot_id=make_slot(db, make_day(db, THURSDAY)).id, held_until=TIDY_AT - timedelta(hours=1)))

    tidied = retention.tidy_up(db, TIDY_AT)

    assert tidied == retention.Tidied(logins=1, setup_codes=1, wrong_tries=1, holds=1)
    assert how_many(db, LoginSession) == how_many(db, SetupCode) == how_many(db, LoginFailure) == 1
    assert db.scalars(select(Hold.student_id)).all() == [later.student_id]
