"""The coordinator changing one pickup day: closing it (S7), opening it again,
and moving its booking times (S9).

Plain Python with a database session, like the other services. The routes in
app/routes/days.py commit. Every change is logged with who made it (R4).

Locks, when closing a day: the day, then all its slots from the lowest id up,
then its bookings, then the food from the lowest id up. Booking locks the slot
before it looks at the day (services/booking.py), so a student pressing Book
while the day is being closed either finishes first, and their booking is
cancelled with the others, or waits, and then sees the day is closed.
Nothing else takes a slot's lock after a booking's, so nobody can end up
waiting for each other forever.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Booking, PickupDay, PickupHours, Slot, Staff, Variety
from app.problems import NotFound, Problem
from app.services import packing
from app.services.booking import UPCOMING
from app.services.pickup_days import NEWFOUNDLAND, make_pickup_day, say_day, say_moment

# How far ahead the coordinator can close a date, like the Christmas break.
FURTHEST_AHEAD = timedelta(days=365)

# Students see the reason: "Monday, November 23 is closed: Snow storm."
REASON_LONGEST = 200


class AlreadyClosed(Problem):
    """Pressing Close twice, or two people closing the same day."""

    status_code = 409


# ---------- closing a day (S7) ----------


@dataclass
class Closed:
    day: PickupDay
    # Bookings cancelled, and how many of them were packed bags.
    cancelled: int
    were_packed: int


def why_not_close(day: PickupDay, now: datetime) -> str | None:
    """Why this day can't be closed, in words. None if it can."""
    if day.closed_at is not None:
        return f"{say_day(day.pickup_date)} is closed already."
    if now >= day.no_show_at:
        return f"{say_day(day.pickup_date)} is over, so it can't be closed."
    return None


def close_day(db: Session, pickup_date: date, reason: str, staff: Staff, now: datetime) -> Closed:
    """Close a pickup day, for a holiday, bad weather or the Christmas break (S7).

    A date further ahead than the pickup days made so far is made first, then
    closed. The jobs script never touches a day that's made, so it stays closed.

    1. Lock the day. It must not be closed already or over.
    2. Lock its slots, so nobody can book while it closes.
    3. Cancel every booking still to come, even packed ones. Their food goes
       back on the stock count: what was booked, or for a packed bag, what's
       really in it (it's unpacked onto the shelf). Their places go back too.
       Cancellations never count toward the pickup gap (F3), so those students
       can book another day.
    4. Mark the day closed, with the reason students will see, and log it.

    Bags already handed over and walk-ins already served stay as they are.
    """
    reason = _tidy_reason(reason)
    day = _lock_day(db, pickup_date)
    if day is None:
        day = _make_to_close(db, pickup_date, now)
    refusal = why_not_close(day, now)
    if refusal is not None:
        raise AlreadyClosed(refusal) if day.closed_at is not None else Problem(refusal)

    # 2.
    slots = {
        slot.id: slot
        for slot in db.scalars(
            select(Slot)
            .where(Slot.pickup_day_id == day.id)
            .order_by(Slot.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    }
    # 3.
    bookings = db.scalars(
        select(Booking)
        .where(Booking.pickup_day_id == day.id, Booking.status.in_(UPCOMING))
        .order_by(Booking.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    contents = {
        booking.id: packing.bag_contents(packing.food_in(db, booking), packing.substitutes_of(db, booking))
        for booking in bookings
    }
    variety_ids = sorted({thing.variety.id for things in contents.values() for thing in things})
    db.scalars(
        select(Variety)
        .where(Variety.id.in_(variety_ids))
        .order_by(Variety.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    were_packed = 0
    for booking in bookings:
        for thing in contents[booking.id]:
            thing.variety.stock += thing.quantity
        slots[booking.slot_id].booked_count -= 1
        were_packed += booking.status == "packed"
        booking.status = "cancelled"
        booking.cancelled_at = now
        booking.cancel_reason = "day_closed"

    # 4.
    day.closed_at = now
    day.closed_reason = reason
    db.add(AuditLog(at=now, staff_id=staff.id, action="closed_day", pickup_day_id=day.id))
    db.flush()
    return Closed(day=day, cancelled=len(bookings), were_packed=were_packed)


def _tidy_reason(reason: str) -> str:
    reason = " ".join(reason.split())
    if not reason:
        raise Problem("Say why it's closed. Students see the reason.")
    if len(reason) > REASON_LONGEST:
        raise Problem(f"Keep the reason to {REASON_LONGEST} characters. Students see it.")
    return reason


def _make_to_close(db: Session, pickup_date: date, now: datetime) -> PickupDay:
    """A date that isn't made yet, like a Monday in the Christmas break: made now, so it can be closed."""
    today = now.astimezone(NEWFOUNDLAND).date()
    if pickup_date <= today:
        raise NotFound(f"There's no pickup on {say_day(pickup_date)}.")
    if pickup_date > today + FURTHEST_AHEAD:
        raise Problem("Dates can be closed up to a year ahead.")
    if db.get(PickupHours, pickup_date.isoweekday()) is None:
        raise Problem(f"{say_day(pickup_date)} isn't a pickup day, so there's nothing to close.")
    return make_pickup_day(db, pickup_date)


# ---------- opening it again ----------


def why_not_reopen(db: Session, day: PickupDay, now: datetime) -> str | None:
    """Why this closed day can't be opened again, in words. None if it can.

    Closing a day cancels its bookings, and a student can't book the same day
    twice (S6). So a day that cancelled bookings stays closed: opened again,
    the students who had booked it couldn't book it any more, and everyone
    else could take their places.
    """
    if day.closed_at is None:
        return f"{say_day(day.pickup_date)} isn't closed."
    if now >= day.no_show_at:
        return f"{say_day(day.pickup_date)} is over."
    cancelled = _cancelled_by_closing(db, day)
    if cancelled:
        said = "1 booking" if cancelled == 1 else f"{cancelled} bookings"
        return (
            f"Closing {say_day(day.pickup_date)} cancelled {said}, so it stays closed: "
            "those students couldn't book it again."
        )
    return None


def reopen_day(db: Session, pickup_date: date, staff: Staff, now: datetime) -> PickupDay:
    """Open a closed day again, like one closed by mistake before anyone booked."""
    day = _lock_day(db, pickup_date)
    if day is None:
        raise NotFound(f"There's no pickup on {say_day(pickup_date)}.")
    refusal = why_not_reopen(db, day, now)
    if refusal is not None:
        raise Problem(refusal)
    day.closed_at = None
    day.closed_reason = None
    db.add(AuditLog(at=now, staff_id=staff.id, action="reopened_day", pickup_day_id=day.id))
    db.flush()
    return day


def _cancelled_by_closing(db: Session, day: PickupDay) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Booking)
        .where(Booking.pickup_day_id == day.id, Booking.cancel_reason == "day_closed")
    )


# ---------- moving one day's booking times (S9) ----------


def why_not_move(day: PickupDay, now: datetime) -> str | None:
    """Why this day's booking times can't be moved, in words. None if they can.

    Only until booking closes. After that, bags are being packed (K1), and
    opening booking again would let students cancel packed bags.
    """
    if day.closed_at is not None:
        return f"{say_day(day.pickup_date)} is closed."
    if now >= day.booking_closes_at:
        return f"Booking for {say_day(day.pickup_date)} is over, and packing has started."
    return None


def move_booking_times(
    db: Session, pickup_date: date, opens_at: datetime, closes_at: datetime, staff: Staff, now: datetime
) -> PickupDay:
    """Move when booking opens and closes for one day, without changing the settings (S9).

    For example, the website was down at 5 pm, so booking opens at 7 pm instead.
    Bookings already made stay. The other days, and the settings, don't change.
    """
    day = _lock_day(db, pickup_date)
    if day is None:
        raise NotFound(f"There's no pickup on {say_day(pickup_date)}.")
    refusal = why_not_move(day, now)
    if refusal is not None:
        raise Problem(refusal)
    if opens_at >= closes_at:
        raise Problem("Booking has to open before it closes.")
    if closes_at <= now:
        raise Problem("The new close time has passed already. Choose a later one.")
    if closes_at > day.pickup_starts_at:
        # No full stop: the time ends in "p.m." already.
        raise Problem(
            f"Booking has to close by the time pickup starts, {say_moment(day.pickup_starts_at)}, "
            "so the bags can be packed"
        )
    day.booking_opens_at = opens_at
    day.booking_closes_at = closes_at
    db.add(AuditLog(at=now, staff_id=staff.id, action="moved_booking_times", pickup_day_id=day.id))
    db.flush()
    return day


# ---------- shared ----------


def _lock_day(db: Session, pickup_date: date) -> PickupDay | None:
    return db.scalar(
        select(PickupDay)
        .where(PickupDay.pickup_date == pickup_date)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
