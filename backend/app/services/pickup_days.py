from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import PickupDay, PickupHours, Settings, Slot

NEWFOUNDLAND = ZoneInfo("America/St_Johns")


def newfoundland_moment(on: date, clock: time) -> datetime:
    """A Newfoundland clock time on a date, as one exact moment (T1).

    The time zone works out the half hour and summer time for that date, so
    5 pm is 20:30 UTC in November and 19:30 UTC in July.
    """
    return datetime.combine(on, clock, tzinfo=NEWFOUNDLAND)


def make_pickup_day(db: Session, pickup_date: date) -> PickupDay:
    """Make one pickup day and its slots, from the settings and the weekly pickup hours.

    The day's booking times are worked out now and saved on the day, so later
    changes to the settings don't move it (S5, S9). Slots are made only inside
    that weekday's pickup hours (S1).
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
        no_show_at=newfoundland_moment(pickup_date, settings.no_show_time),
    )
    db.add(day)
    db.flush()

    slot_length = timedelta(minutes=settings.slot_minutes)
    starts_at = newfoundland_moment(pickup_date, hours.starts_at)
    pickup_ends_at = newfoundland_moment(pickup_date, hours.ends_at)
    while starts_at + slot_length <= pickup_ends_at:
        db.add(Slot(pickup_day_id=day.id, starts_at=starts_at, capacity=settings.slot_capacity))
        starts_at += slot_length
    db.flush()
    return day
