"""Weekly totals for the coordinator (P7, P12): saved weeks plus the days still on record.

The week of Monday 2 November was saved already: its details are gone. The
week of Monday 9 November is still on record: Monday 9 and Thursday 12.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.models import Booking, BookingItem, Category, Item, Slot, Variety, WalkIn, WeeklyItemTotal, WeeklyTotal
from app.services import totals
from app.services.pickup_days import make_pickup_day
from tests.helpers import MONDAY, THURSDAY, add, coordinator, log_in, make_staff, make_student, stop_the_clock_at

THURSDAY_5PM = datetime(2026, 11, 12, 20, 30, tzinfo=UTC)  # pickup is still on
THURSDAY_7PM = datetime(2026, 11, 12, 22, 30, tzinfo=UTC)  # Thursday is over
LAST_WEEK = date(2026, 11, 2)
CODES = iter(f"K{n}P" for n in range(2, 10))


def bag(db, day, status: str, *varieties: Variety, code: str | None = None) -> Booking:
    """A booking on that day, with its times filled in for its status."""
    staff = make_staff(db)
    slot = db.query(Slot).filter(Slot.pickup_day_id == day.id).first()
    when = day.pickup_starts_at
    columns = {
        "packed": dict(packed_at=when, packed_by_staff_id=staff.id),
        "picked_up": dict(
            packed_at=when, packed_by_staff_id=staff.id, picked_up_at=when, picked_up_by_staff_id=staff.id
        ),
        "no_show": dict(packed_at=when, packed_by_staff_id=staff.id, no_show_at=day.no_show_at),
        "cancelled": dict(cancelled_at=when, cancel_reason="student"),
    }[status]
    booking = add(
        db,
        Booking(
            student_id=make_student(db).id,
            pickup_day_id=day.id,
            slot_id=slot.id,
            code=code or next(CODES),
            status=status,
            **columns,
        ),
    )
    for variety in varieties:
        add(db, BookingItem(booking_id=booking.id, variety_id=variety.id))
    return booking


@pytest.fixture
def weeks(db_with_sample_week):
    """Monday 9: 6 picked up with oats, 2 no-shows, 1 cancelled, 1 walk-in.
    Thursday 12: 1 picked up with oats and rice. Last week: saved totals."""
    db = db_with_sample_week
    pantry = add(db, Category(name="Pantry"))
    oats_item = add(db, Item(name="Oats", category_id=pantry.id))
    rice_item = add(db, Item(name="Rice", category_id=pantry.id))
    oats = add(db, Variety(item_id=oats_item.id, name="Quick oats", stock=50))
    rice = add(db, Variety(item_id=rice_item.id, name="White rice", stock=50))

    monday, thursday = make_pickup_day(db, MONDAY), make_pickup_day(db, THURSDAY)
    for n in range(6):
        bag(db, monday, "picked_up", oats, code=f"A{n + 2}A")
    bag(db, monday, "no_show", oats, code="B2B")
    bag(db, monday, "no_show", rice, code="B3B")
    bag(db, monday, "cancelled", rice, code="C2C")
    add(db, WalkIn(student_id=make_student(db).id, pickup_day_id=monday.id, served_at=monday.pickup_starts_at, served_by_staff_id=make_staff(db).id))
    bag(db, thursday, "picked_up", oats, rice, code="D2D")

    add(db, WeeklyTotal(week_starts_on=LAST_WEEK, picked_up=7, walk_ins=3, no_shows=0, cancelled=5))
    add(db, WeeklyItemTotal(week_starts_on=LAST_WEEK, item_id=oats_item.id, given_out=10))
    add(db, WeeklyItemTotal(week_starts_on=LAST_WEEK, item_id=rice_item.id, given_out=2))
    return {"oats": oats_item.id, "rice": rice_item.id}


def test_a_week_is_its_saved_totals_or_its_days_still_on_record(db, weeks):
    found = totals.weeks(db, THURSDAY_7PM)

    assert list(found) == [MONDAY, LAST_WEEK]
    this_week = found[MONDAY]
    assert (this_week.picked_up, this_week.walk_ins, this_week.no_shows, this_week.cancelled) == (7, 1, 2, 1)
    assert this_week.given_out == {weeks["oats"]: 7, weeks["rice"]: 1}
    last_week = found[LAST_WEEK]
    assert (last_week.picked_up, last_week.walk_ins, last_week.no_shows, last_week.cancelled) == (7, 3, 0, 5)
    assert last_week.given_out == {weeks["oats"]: 10, weeks["rice"]: 2}


def test_a_day_counts_once_it_is_over(db, weeks):
    this_week = totals.weeks(db, THURSDAY_5PM)[MONDAY]

    assert this_week.picked_up == 6
    assert this_week.given_out == {weeks["oats"]: 6}


def test_the_coordinator_sees_fewer_than_5_for_1_to_4(client, db_with_sample_week, weeks):
    """P12: the real small number never leaves the server. 0 shows as 0."""
    log_in(client, db_with_sample_week, coordinator(db_with_sample_week), THURSDAY_7PM)
    stop_the_clock_at(THURSDAY_7PM)

    page = client.get("/api/totals").json()

    assert page == {
        "weeks": [
            {
                "week_starts_on": "2026-11-09",
                "picked_up": 7,
                "walk_ins": "fewer than 5",
                "no_shows": "fewer than 5",
                "cancelled": "fewer than 5",
                "items": [{"item": "Oats", "given_out": 7}, {"item": "Rice", "given_out": "fewer than 5"}],
            },
            {
                "week_starts_on": "2026-11-02",
                "picked_up": 7,
                "walk_ins": "fewer than 5",
                "no_shows": 0,
                "cancelled": 5,
                "items": [{"item": "Oats", "given_out": 10}, {"item": "Rice", "given_out": "fewer than 5"}],
            },
        ]
    }


def test_no_weeks_yet(client, db_with_sample_week):
    log_in(client, db_with_sample_week, coordinator(db_with_sample_week), THURSDAY_7PM)

    assert client.get("/api/totals").json() == {"weeks": []}


def test_only_1_to_4_are_hidden():
    from app.routes.totals import shown

    assert [shown(n) for n in [0, 1, 4, 5, 12]] == [0, "fewer than 5", "fewer than 5", 5, 12]


def test_small_numbers_come_last_a_to_z_so_their_order_says_nothing():
    from app.routes.totals import _items

    names = {1: "Rice", 2: "Beans", 3: "Oats", 4: "Pasta"}
    listed = _items({1: 4, 2: 1, 3: 9, 4: 12}, names)

    assert [(line.item, line.given_out) for line in listed] == [
        ("Pasta", 12),
        ("Oats", 9),
        ("Beans", "fewer than 5"),
        ("Rice", "fewer than 5"),
    ]


def test_weeks_start_on_monday(db, weeks):
    assert totals.week_of(THURSDAY) == MONDAY
    assert totals.week_of(MONDAY + timedelta(days=6)) == MONDAY
