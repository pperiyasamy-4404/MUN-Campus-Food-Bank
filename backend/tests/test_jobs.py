"""The jobs script (app/jobs.py): making pickup days ahead of time, and running every job in turn.

Each job's own rules are tested in test_no_shows.py and test_retention.py.
The runner commits, so its tests use committed rows and delete them afterwards.
"""

from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app import jobs
from app.models import (
    Booking,
    BookingItem,
    Category,
    Item,
    PickupDay,
    Settings,
    Slot,
    Staff,
    Student,
    Variety,
    WeeklyItemTotal,
    WeeklyTotal,
)
from app.sample_data import SAMPLE_SETTINGS
from app.services.pickup_days import make_days_ahead, make_pickup_day
from tests.helpers import MONDAY, THURSDAY

MONDAY_MORNING = datetime(2026, 11, 9, 13, 0, tzinfo=UTC)  # Monday 9 November 2026, 9:30 am in St. John's


# ---------- making pickup days ahead of time ----------


def test_pickup_days_are_made_a_week_ahead(db_with_sample_week):
    db = db_with_sample_week

    made = make_days_ahead(db, MONDAY_MORNING)

    # From tomorrow to a week from today, on Mondays and Thursdays. Not today.
    assert [day.pickup_date for day in made] == [date(2026, 11, 12), date(2026, 11, 16)]
    assert make_days_ahead(db, MONDAY_MORNING) == []


def test_a_day_already_made_is_left_as_it_is(db_with_sample_week):
    """Even if the coordinator closed it (S7): it isn't made again."""
    db = db_with_sample_week
    thursday = make_pickup_day(db, THURSDAY)
    thursday.closed_at, thursday.closed_reason = MONDAY_MORNING, "Exam week"
    db.flush()

    made = make_days_ahead(db, MONDAY_MORNING)

    assert THURSDAY not in [day.pickup_date for day in made]
    assert db.scalar(select(PickupDay.closed_reason).where(PickupDay.pickup_date == THURSDAY)) == "Exam week"


# ---------- the whole run ----------

# Far from the other tests' dates, so these committed rows can't meet theirs.
RECENT = MONDAY + timedelta(days=2002)  # a Monday
OLD = RECENT - timedelta(days=98)  # a Monday, past the 90 days
RUN_AT = datetime.combine(RECENT, time(23, 0), tzinfo=UTC)  # 7:30 pm in St. John's


def a_day(db, on: date) -> PickupDay:
    """A pickup day with the sample times, as if made long ago, without its slots."""
    noon = datetime.combine(on, time(15, 30), tzinfo=UTC)  # 12 pm in St. John's, in winter
    day = PickupDay(
        pickup_date=on,
        booking_opens_at=noon - timedelta(hours=19),
        booking_closes_at=noon,
        pickup_starts_at=noon + timedelta(hours=3, minutes=30),
        pickup_ends_at=noon + timedelta(hours=5, minutes=30),
        no_show_at=noon + timedelta(hours=6),
    )
    db.add(day)
    db.flush()
    return day


@pytest.fixture
def world(engine):
    """Committed: the settings, but no weekly pickup hours, so no days are made.
    - RECENT: a packed bag of oats nobody picked up.
    - OLD: a bag of oats picked up 98 days ago.
    - A student whose last pickup was 400 days ago, with nothing on record.
    """
    with Session(engine) as db:
        db.add(Settings(**SAMPLE_SETTINGS))
        staff = Staff(username="Jobs volunteer", role="volunteer")
        category = Category(name="Jobs shelf")
        db.add_all([staff, category])
        db.flush()
        item = Item(name="Jobs oats", category_id=category.id)
        db.add(item)
        db.flush()
        oats = Variety(item_id=item.id, name="Jobs quick oats", stock=3)
        recent, old = a_day(db, RECENT), a_day(db, OLD)
        # Handing over a bag sets the student's last pickup date, so the old one has it.
        students = [
            Student(id_hash="e" * 64, created_by_staff_id=staff.id),
            Student(id_hash="f" * 64, created_by_staff_id=staff.id, last_pickup_on=OLD),
        ]
        quiet = Student(id_hash="9" * 64, created_by_staff_id=staff.id, last_pickup_on=RECENT - timedelta(days=400))
        db.add_all([oats, *students, quiet])
        db.flush()
        bags = []
        for day, student, status in [(recent, students[0], "packed"), (old, students[1], "picked_up")]:
            slot = Slot(pickup_day_id=day.id, starts_at=day.pickup_starts_at, capacity=1, booked_count=1)
            db.add(slot)
            db.flush()
            moment = day.pickup_starts_at
            bag = Booking(
                student_id=student.id,
                pickup_day_id=day.id,
                slot_id=slot.id,
                code="J5K",
                status=status,
                packed_at=moment,
                packed_by_staff_id=staff.id,
                picked_up_at=moment if status == "picked_up" else None,
                picked_up_by_staff_id=staff.id if status == "picked_up" else None,
            )
            db.add(bag)
            db.flush()
            db.add(BookingItem(booking_id=bag.id, variety_id=oats.id))
            bags.append(bag.id)
        db.commit()
        ids = {
            "bags": bags,
            "oats": oats.id,
            "item": item.id,
            "category": category.id,
            "days": [recent.id, old.id],
            "students": [s.id for s in [*students, quiet]],
            "quiet": quiet.id,
            "staff": staff.id,
        }
    yield ids
    with engine.begin() as tidy:
        tidy.execute(delete(WeeklyItemTotal).where(WeeklyItemTotal.week_starts_on == OLD))
        tidy.execute(delete(WeeklyTotal).where(WeeklyTotal.week_starts_on == OLD))
        tidy.execute(delete(Booking).where(Booking.id.in_(ids["bags"])))
        tidy.execute(delete(Slot).where(Slot.pickup_day_id.in_(ids["days"])))
        tidy.execute(delete(PickupDay).where(PickupDay.id.in_(ids["days"])))
        tidy.execute(delete(Variety).where(Variety.id == ids["oats"]))
        tidy.execute(delete(Item).where(Item.id == ids["item"]))
        tidy.execute(delete(Category).where(Category.id == ids["category"]))
        tidy.execute(delete(Student).where(Student.id.in_(ids["students"])))
        tidy.execute(delete(Staff).where(Staff.id == ids["staff"]))
        tidy.execute(delete(Settings))


def test_a_run_does_what_is_due_and_a_second_run_does_nothing(engine, world):
    report = jobs.run_jobs(engine, RUN_AT)

    assert report.lines() == [
        "1 no-show. Their food is back on the shelf.",
        "Saved the totals and deleted the booking details of 1 pickup day.",
        "Deleted 1 account with no pickup for a year.",
    ]
    with Session(engine) as check:
        recent_bag, old_bag = (check.get(Booking, bag) for bag in world["bags"])
        assert recent_bag.status == "no_show"
        assert old_bag is None
        assert check.get(Variety, world["oats"]).stock == 4
        assert check.get(WeeklyTotal, OLD).picked_up == 1
        assert check.get(Student, world["quiet"]) is None
        # The student whose old details were deleted is still here: their last pickup was 98 days ago.
        assert check.get(Student, world["students"][1]) is not None

    assert jobs.run_jobs(engine, RUN_AT + timedelta(minutes=15)).lines() == ["Nothing was due."]


def test_only_one_run_at_a_time(engine, world):
    """A run started while another is still going does nothing."""
    with engine.connect() as other_run:
        other_run.execute(text("SELECT pg_advisory_lock(hashtextextended(:name, 0))"), {"name": jobs.LOCK_NAME})
        try:
            report = jobs.run_jobs(engine, RUN_AT)
        finally:
            other_run.execute(text("SELECT pg_advisory_unlock(hashtextextended(:name, 0))"), {"name": jobs.LOCK_NAME})

    assert report.lines() == ["Another jobs run is still going, so this one did nothing."]
    with Session(engine) as check:
        assert check.get(Booking, world["bags"][0]).status == "packed"


def test_a_job_that_fails_doesnt_stop_the_others(engine, world, monkeypatch):
    def broken(db, booking_id, now):
        raise RuntimeError("something broke")

    monkeypatch.setattr(jobs.no_shows, "mark_no_show", broken)

    report = jobs.run_jobs(engine, RUN_AT)

    assert report.problems == ["No-shows failed: RuntimeError: something broke"]
    assert report.days_deleted == 1
    assert report.accounts_deleted == 1


def test_without_settings_nothing_is_done(engine):
    report = jobs.run_jobs(engine, RUN_AT)

    assert report.lines() == ["The food bank settings aren't in the database yet, so nothing was done."]
