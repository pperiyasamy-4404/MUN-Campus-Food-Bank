"""The food bank's numbers: the one row of the settings table, and the weekly pickup hours.

The coordinator changes them on the Settings page (R3, step 9). Some are used
straight away, like the pickup gap and the item limit. The ones that make
pickup days, like booking times and pickup hours, are copied onto each day
when it's made, a week ahead (services/pickup_days.py). So a day already
made keeps its times: changing the settings never moves a day students can
already see.

One exception, the user's answer of 10 November: students per slot also
changes on days already made whose booking hasn't opened yet. It's raised in
a rush, when many students need food, and a week is too long to wait.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models import AuditLog, PickupDay, PickupHours, Settings, Slot, Staff
from app.problems import Problem
from app.services.pickup_days import DAYS_AHEAD, say_time

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Every number on the Settings page, as named in the settings table.
SETTING_NAMES = [
    "pickup_gap_days",
    "slot_minutes",
    "slot_capacity",
    "hold_minutes",
    "item_limit",
    "max_per_item",
    "substitute_limit",
    "booking_opens_days_before",
    "booking_opens_time",
    "booking_closes_time",
    "no_show_time",
    "no_shows_count",
    "retention_days",
    "setup_code_days",
    "login_tries",
    "login_window_minutes",
]

# Booking has to open after the day is made, or the first students would find
# booking already open. Days are made a week ahead, from tomorrow.
MOST_DAYS_BEFORE = DAYS_AHEAD.days - 1


def food_bank_settings(db: Session) -> Settings:
    settings = db.get(Settings, 1)
    if settings is None:
        raise LookupError("The settings row is missing")
    return settings


@dataclass(frozen=True)
class WeeklyHours:
    """Pickups on one weekday, like Monday 3:30 to 5:30 pm. 1 is Monday, 7 is Sunday."""

    weekday: int
    starts_at: time
    ends_at: time


def weekly_hours(db: Session) -> list[WeeklyHours]:
    return [
        WeeklyHours(row.weekday, row.starts_at, row.ends_at)
        for row in db.scalars(select(PickupHours).order_by(PickupHours.weekday))
    ]


def why_not_fit(values: dict, hours: list[WeeklyHours]) -> str | None:
    """Why these settings and weekly hours don't work together, in words. None if they do.

    Each single number is checked on its own before this (routes/settings.py).
    These are the rules between them. The database checks the same ones it
    can, but a sentence is more use to the coordinator than a refusal.
    """
    if values["max_per_item"] > values["item_limit"]:
        return "The most of one item can't be more than the item limit."
    if values["retention_days"] < values["pickup_gap_days"]:
        return (
            "Booking details have to be kept at least as long as the pickup gap. "
            "Otherwise a pickup could be deleted while it still counts."
        )
    if values["booking_opens_days_before"] == 0 and values["booking_opens_time"] >= values["booking_closes_time"]:
        return "Booking opens and closes on the same day, so it has to open before it closes."
    if values["booking_opens_days_before"] > MOST_DAYS_BEFORE:
        return f"Booking can open at most {MOST_DAYS_BEFORE} days before, because days are made a week ahead."

    if not hours:
        return "Choose at least one pickup day of the week. To stop for a while, close the days instead."
    if len({day.weekday for day in hours}) != len(hours):
        return "Each day of the week can have one set of pickup hours."
    closes, no_show = values["booking_closes_time"], values["no_show_time"]
    slot = timedelta(minutes=values["slot_minutes"])
    for day in hours:
        name = WEEKDAYS[day.weekday - 1]
        # A time ends in "a.m." or "p.m." already, so no full stop follows it below.
        if day.ends_at <= day.starts_at:
            return f"{name}: pickup has to end after it starts."
        if closes > day.starts_at:
            return (
                f"{name}: booking closes at {say_time(closes)}, after pickup starts at {say_time(day.starts_at)} "
                "It has to close first, so the bags can be packed."
            )
        if day.ends_at > no_show:
            return (
                f"{name}: pickup ends at {say_time(day.ends_at)}, after the no-show time, {say_time(no_show)} "
                "No-shows have to come after pickup ends."
            )
        length = datetime.combine(date.min, day.ends_at) - datetime.combine(date.min, day.starts_at)
        if length < slot:
            return f"{name}: the pickup hours are shorter than one {values['slot_minutes']}-minute slot."
    return None


def change_settings(db: Session, values: dict, hours: list[WeeklyHours], staff: Staff, now: datetime) -> list[date]:
    """Save new settings and weekly hours, and log who changed them (R3, R4).

    Days already made keep their own times. New days, made by the jobs
    script, use the new ones. A new number of students per slot also reaches
    days already made whose booking hasn't opened. Returns those days.
    """
    if set(values) != set(SETTING_NAMES):
        raise ValueError("Every setting has to be given")
    reason = why_not_fit(values, hours)
    if reason is not None:
        raise Problem(reason)

    # Locked, so two people saving at once take turns, and the second one's values win whole.
    settings = db.scalar(
        select(Settings).where(Settings.id == 1).with_for_update().execution_options(populate_existing=True)
    )
    if settings is None:
        raise LookupError("The settings row is missing")
    capacity_changed = settings.slot_capacity != values["slot_capacity"]
    for name in SETTING_NAMES:
        setattr(settings, name, values[name])
    db.execute(delete(PickupHours))
    db.add_all(PickupHours(weekday=day.weekday, starts_at=day.starts_at, ends_at=day.ends_at) for day in hours)
    changed_days = new_capacity_on_days_not_open(db, values["slot_capacity"], now) if capacity_changed else []
    db.add(AuditLog(at=now, staff_id=staff.id, action="changed_settings"))
    db.flush()
    return changed_days


def new_capacity_on_days_not_open(db: Session, capacity: int, now: datetime) -> list[date]:
    """Students per slot, on every day already made whose booking hasn't opened yet.

    Before booking opens, nobody holds or books a slot, so nothing changes
    under a student's feet. A slot never goes below what's booked in it: the
    coordinator can move a day's opening later after some students booked (S9),
    and the database refuses going over capacity (S2).
    """
    not_open = select(PickupDay.id).where(PickupDay.booking_opens_at > now)
    db.execute(
        update(Slot)
        .where(Slot.pickup_day_id.in_(not_open))
        .values(capacity=func.greatest(capacity, Slot.booked_count))
        .execution_options(synchronize_session=False)
    )
    return list(db.scalars(select(PickupDay.pickup_date).where(PickupDay.id.in_(not_open)).order_by(PickupDay.pickup_date)))
