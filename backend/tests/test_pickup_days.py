from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import select

from app.models import PickupHours, Settings, Slot
from app.sample_data import SAMPLE_PICKUP_HOURS
from app.services.pickup_days import NEWFOUNDLAND, make_pickup_day
from tests.helpers import add, make_settings


@pytest.fixture
def db_with_sample_week(db):
    """The sample settings, with pickups on Monday and Thursday, 3:30 to 5:30 pm."""
    make_settings(db)
    for weekday, starts_at, ends_at in SAMPLE_PICKUP_HOURS:
        add(db, PickupHours(weekday=weekday, starts_at=starts_at, ends_at=ends_at))
    return db


def utc(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def slots_of(db, day):
    return db.scalars(select(Slot).where(Slot.pickup_day_id == day.id).order_by(Slot.starts_at)).all()


def test_a_monday_in_november(db_with_sample_week):
    """Newfoundland is UTC-3:30 in winter, so 5 pm is 20:30 UTC."""
    db = db_with_sample_week
    day = make_pickup_day(db, date(2026, 11, 9))
    db.refresh(day)

    assert day.booking_opens_at == utc(2026, 11, 8, 20, 30)  # Sunday 5 pm
    assert day.booking_closes_at == utc(2026, 11, 9, 15, 30)  # Monday 12 pm
    assert day.no_show_at == utc(2026, 11, 9, 21, 30)  # Monday 6 pm


def test_twelve_ten_minute_slots_from_3_30_to_5_30(db_with_sample_week):
    db = db_with_sample_week
    slots = slots_of(db, make_pickup_day(db, date(2026, 11, 9)))

    starts = [slot.starts_at.astimezone(NEWFOUNDLAND) for slot in slots]
    assert len(slots) == 12
    assert starts[0].time() == time(15, 30)
    assert starts[-1].time() == time(17, 20)
    assert {later - earlier for earlier, later in zip(starts, starts[1:])} == {timedelta(minutes=10)}
    assert {slot.capacity for slot in slots} == {1}


def test_a_monday_in_summer(db_with_sample_week):
    """In summer Newfoundland is UTC-2:30, so 5 pm is 19:30 UTC."""
    day = make_pickup_day(db_with_sample_week, date(2026, 7, 6))
    assert day.booking_opens_at == utc(2026, 7, 5, 19, 30)


def test_booking_opens_on_the_day_the_clocks_go_back(db_with_sample_week):
    """The clocks went back at 2 am on Sunday 1 November. Booking opens that evening, in winter time."""
    day = make_pickup_day(db_with_sample_week, date(2026, 11, 2))
    assert day.booking_opens_at == utc(2026, 11, 1, 20, 30)


def test_a_tuesday_is_not_a_pickup_day(db_with_sample_week):
    with pytest.raises(ValueError, match="not a pickup day"):
        make_pickup_day(db_with_sample_week, date(2026, 11, 10))


def test_slots_take_their_capacity_from_the_settings(db_with_sample_week):
    db = db_with_sample_week
    db.get(Settings, 1).slot_capacity = 2
    slots = slots_of(db, make_pickup_day(db, date(2026, 11, 12)))
    assert {slot.capacity for slot in slots} == {2}


def test_changing_the_settings_does_not_move_a_day_already_made(db_with_sample_week):
    """Choice D: each day keeps its own times, so a settings change can't move it."""
    db = db_with_sample_week
    day = make_pickup_day(db, date(2026, 11, 9))
    db.get(Settings, 1).booking_opens_time = time(18, 0)
    db.flush()
    db.refresh(day)
    assert day.booking_opens_at == utc(2026, 11, 8, 20, 30)
