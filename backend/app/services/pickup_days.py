from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PickupDay, PickupHours, Settings, Slot

NEWFOUNDLAND = ZoneInfo("America/St_Johns")

# How far ahead the jobs script makes pickup days. One week (the user's answer, 10 Nov).
DAYS_AHEAD = timedelta(days=7)

BookingStatus = Literal["not_open_yet", "open", "booking_over", "day_closed"]


def newfoundland_moment(on: date, clock: time) -> datetime:
    """A Newfoundland clock time on a date, as one exact moment (T1).

    The time zone works out the half hour and summer time for that date, so
    5 pm is 20:30 UTC in November and 19:30 UTC in July.
    """
    return datetime.combine(on, clock, tzinfo=NEWFOUNDLAND)


def make_pickup_day(db: Session, pickup_date: date) -> PickupDay:
    """Make one pickup day and its slots, from the settings and the weekly pickup hours.

    The day's booking times and pickup hours are worked out now and saved on the
    day, so later changes to the settings or the weekly hours don't move it
    (S5, S9). Slots are made only inside the pickup hours (S1).
    """
    settings = db.get(Settings, 1)
    if settings is None:
        raise LookupError("The settings row is missing")
    hours = db.get(PickupHours, pickup_date.isoweekday())
    if hours is None:
        raise ValueError(f"{pickup_date:%A %d %B} is not a pickup day")

    opens_on = pickup_date - timedelta(days=settings.booking_opens_days_before)
    day = PickupDay(
        pickup_date=pickup_date,
        booking_opens_at=newfoundland_moment(opens_on, settings.booking_opens_time),
        booking_closes_at=newfoundland_moment(pickup_date, settings.booking_closes_time),
        pickup_starts_at=newfoundland_moment(pickup_date, hours.starts_at),
        pickup_ends_at=newfoundland_moment(pickup_date, hours.ends_at),
        no_show_at=newfoundland_moment(pickup_date, settings.no_show_time),
    )
    db.add(day)
    db.flush()

    slot_length = timedelta(minutes=settings.slot_minutes)
    starts_at = day.pickup_starts_at
    while starts_at + slot_length <= day.pickup_ends_at:
        db.add(Slot(pickup_day_id=day.id, starts_at=starts_at, capacity=settings.slot_capacity))
        starts_at += slot_length
    db.flush()
    return day


def make_days_ahead(db: Session, now: datetime) -> list[PickupDay]:
    """Make the pickup days for the next week that aren't made yet (S1).

    From tomorrow, so a day is never made after its booking has opened. A day
    already made is never touched, even if the coordinator closed it (S7).
    A week, so a change to the settings reaches new days within a week. Dates
    further ahead can still be closed: the coordinator's page makes them first (S7).
    """
    today = now.astimezone(NEWFOUNDLAND).date()
    weekdays = set(db.scalars(select(PickupHours.weekday)))
    made_already = set(
        db.scalars(select(PickupDay.pickup_date).where(PickupDay.pickup_date > today, PickupDay.pickup_date <= today + DAYS_AHEAD))
    )
    made = []
    for ahead in range(1, DAYS_AHEAD.days + 1):
        on = today + timedelta(days=ahead)
        if on.isoweekday() in weekdays and on not in made_already:
            made.append(make_pickup_day(db, on))
    return made


def booking_status(day: PickupDay, now: datetime) -> BookingStatus:
    """Where a pickup day's booking is at this moment (S5, S7).

    Booking opens exactly at the open time and is over exactly at the close time:
    with the sample settings, 5:00 pm the day before is open, 12:00 pm is over.
    A day the coordinator closed stays closed, whatever the time.
    """
    if day.closed_at is not None:
        return "day_closed"
    if now < day.booking_opens_at:
        return "not_open_yet"
    if now < day.booking_closes_at:
        return "open"
    return "booking_over"


def say_day(on: date) -> str:
    """'Monday, November 9', for messages people read. Matches the page's dates."""
    return f"{on:%A, %B} {on.day}"


def say_clock(moment: datetime) -> str:
    """'3:30 p.m.', in Newfoundland time (T1)."""
    return say_time(moment.astimezone(NEWFOUNDLAND).time())


def say_time(clock: time) -> str:
    """'3:30 p.m.', for a time of day like the ones in the settings."""
    return f"{clock:%I:%M}".lstrip("0") + (" a.m." if clock.hour < 12 else " p.m.")


def say_moment(moment: datetime) -> str:
    """'Monday, November 9 at 3:30 p.m.', in Newfoundland time (T1)."""
    return f"{say_day(moment.astimezone(NEWFOUNDLAND).date())} at {say_clock(moment)}"
