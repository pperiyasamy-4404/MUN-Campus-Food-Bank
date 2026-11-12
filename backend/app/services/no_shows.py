"""No-shows (B3, I6), and fixing a pickup that was marked wrong (B6).

Plain Python with a database session, like the other services. The jobs script
(app/jobs.py) and the routes in app/routes/fixes.py commit.

A booking not picked up by the no-show time becomes a no-show. The system does
this by itself: the jobs script runs every 15 minutes and finds every booking
that's due, so a run that was missed is caught up by the next one.

What goes back on the shelf is what was really in the bag (packing.bag_contents):
- a bag that was never packed: the booked food, which was taken off stock at Book
- a packed bag: the booked food that was on the shelf, plus the substitutes that went in

Locks, in the same order as everywhere else: the student, then the booking,
then the food from the lowest id up. So a volunteer pressing Hand over at the
last second and the no-show job take turns, and the bag is one or the other.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Booking, CounterItem, PickupDay, Slot, Staff, Student, Variety, WalkIn
from app.problems import NotFound, Problem
from app.services import packing
from app.services.booking import UPCOMING
from app.services.counter import count_pickup
from app.services.pickup_days import say_clock, say_day
from app.services.settings import food_bank_settings


# A fix moves a bag between these two, one way or the other (B2, B6).
FIXABLE = ("no_show", "picked_up")


class CantFix(Problem):
    """The bag isn't in the state the fix starts from: maybe someone fixed it a moment ago."""

    status_code = 409


# ---------- the no-show job (B3, I6) ----------


def due_no_shows(db: Session, now: datetime) -> list[int]:
    """Bookings still booked or packed on a day whose no-show time has come.

    A closed day is left out: nobody is a no-show on a day the food bank closed.
    Closing a day cancels its bookings (S7, step 9).
    """
    return list(
        db.scalars(
            select(Booking.id)
            .join(PickupDay, PickupDay.id == Booking.pickup_day_id)
            .where(Booking.status.in_(UPCOMING), PickupDay.no_show_at <= now, PickupDay.closed_at.is_(None))
            .order_by(Booking.id)
        )
    )


def mark_no_show(db: Session, booking_id: int, now: datetime) -> Booking | None:
    """One booking becomes a no-show, and its food goes back on the shelf (I6).

    None if there was nothing to do: it was picked up a moment ago, or it isn't due.
    The no-show time saved is the day's, not when the job happened to run.
    """
    found = db.get(Booking, booking_id)
    if found is None:
        return None
    _lock_student(db, found.student_id)
    booking = _lock_booking(db, booking_id)
    day = db.get(PickupDay, booking.pickup_day_id)
    if booking.status not in UPCOMING or now < day.no_show_at or day.closed_at is not None:
        return None

    contents = _contents(db, booking)
    _lock_food(db, {thing.variety.id for thing in contents})
    for thing in contents:
        thing.variety.put_back(thing.quantity)
    booking.status = "no_show"
    booking.no_show_at = day.no_show_at
    db.flush()
    return booking


# ---------- fixing a mistake afterwards (B6) ----------


def why_not_fix(booking: Booking, day: PickupDay, now: datetime) -> str | None:
    """Why this bag can't be fixed, in words. None if it can.

    Only once the day is over: until then, a bag that wasn't handed over isn't
    a no-show yet. Only between no-show and picked up (B2).
    """
    if now < day.no_show_at:
        # No full stop: the time ends in "p.m." already.
        return f"Pickups for {say_day(day.pickup_date)} can be fixed once the day is over, at {say_clock(day.no_show_at)}"
    if booking.status not in FIXABLE:
        return f"Bag {booking.code} isn't a no-show or picked up, so there's nothing to fix."
    if booking.status == "no_show" and booking.packed_at is None:
        return f"Bag {booking.code} was never packed, so it can't have been handed over."
    return None


@dataclass
class FixedToPickedUp:
    booking: Booking
    # Their later booking, cancelled because it's now too soon after this pickup.
    cancelled: Booking | None
    cancelled_on: date | None


def fix_to_picked_up(db: Session, booking_id: int, staff: Staff, now: datetime) -> FixedToPickedUp:
    """A no-show that was really handed over: the volunteer forgot to press Hand over (B6).

    1. Lock the student, then the booking. It must still be a no-show.
    2. A later booking now less than the pickup gap after this pickup is
       cancelled (decided 12 Nov). Example: Monday's bag was handed over but
       marked a no-show, so the student booked Thursday. Fixing Monday to picked
       up cancels Thursday, or they'd get two bags in 3 days. Locked like a
       cancel: the slot, then that booking.
    3. The food in the bag left with the student, so it comes off stock again.
       If the count is already lower, it stops at 0: the shelf can't have less than none.
       Food with no number keeps no number. The cancelled booking's food goes back.
    4. Picked up, recorded as by this volunteer, now. The pickup gap counts from that day (F1).
    5. Logged with who fixed it, and the cancel too.
    """
    booking, day = _start_fix(db, booking_id, "no_show", now)
    student = db.get(Student, booking.student_id)

    # 2.
    gap_ends = day.pickup_date + timedelta(days=food_bank_settings(db).pickup_gap_days)
    too_soon, too_soon_on, slot = None, None, None
    later = db.scalar(select(Booking).where(Booking.student_id == student.id, Booking.status.in_(UPCOMING)))
    if later is not None:
        later_on = db.get(PickupDay, later.pickup_day_id).pickup_date
        if later_on < gap_ends:
            slot = db.scalar(select(Slot).where(Slot.id == later.slot_id).with_for_update())
            locked = _lock_booking(db, later.id)
            if locked.status in UPCOMING:
                too_soon, too_soon_on = locked, later_on

    # 3.
    contents = _contents(db, booking)
    returned = _contents(db, too_soon) if too_soon is not None else []
    _lock_food(db, {thing.variety.id for thing in contents} | {thing.variety.id for thing in returned})
    for thing in contents:
        thing.variety.take(min(thing.quantity, thing.variety.stock or 0))
    if too_soon is not None:
        for thing in returned:
            thing.variety.put_back(thing.quantity)
        slot.booked_count -= 1
        too_soon.status = "cancelled"
        too_soon.cancelled_at = now
        too_soon.cancel_reason = "pickup_fixed"
        db.add(AuditLog(at=now, staff_id=staff.id, action="cancelled_too_soon", student_id=student.id, booking_id=too_soon.id))

    booking.status = "picked_up"
    booking.no_show_at = None
    booking.picked_up_at = now
    booking.picked_up_by_staff_id = staff.id
    count_pickup(student, day)
    db.add(
        AuditLog(at=now, staff_id=staff.id, action="fixed_no_show_to_picked_up", student_id=student.id, booking_id=booking.id)
    )
    db.flush()
    return FixedToPickedUp(booking=booking, cancelled=too_soon, cancelled_on=too_soon_on)


def fix_to_no_show(db: Session, booking_id: int, staff: Staff, now: datetime) -> Booking:
    """A bag marked picked up that the student never took (B6).

    1. Lock the student, then the booking. It must still be picked up.
    2. Everything recorded as handed over goes back on the shelf: the bag, and
       anything given at the counter with it (extras, choices for a gap). Those
       counter rows are deleted, because they didn't happen.
    3. A no-show, at the day's no-show time.
    4. The pickup gap counts from their last real pickup still on record, if any (F1).
    5. Logged with who fixed it. The log still has who marked it picked up.
    """
    booking, day = _start_fix(db, booking_id, "picked_up", now)
    student = db.get(Student, booking.student_id)

    contents = _contents(db, booking)
    at_counter = db.scalars(select(CounterItem).where(CounterItem.booking_id == booking.id)).all()
    _lock_food(db, {thing.variety.id for thing in contents} | {row.variety_id for row in at_counter})
    for thing in contents:
        thing.variety.put_back(thing.quantity)
    for row in at_counter:
        db.get(Variety, row.variety_id).put_back(row.quantity)
    db.execute(delete(CounterItem).where(CounterItem.booking_id == booking.id))

    booking.status = "no_show"
    booking.no_show_at = day.no_show_at
    booking.picked_up_at = None
    booking.picked_up_by_staff_id = None
    db.flush()
    student.last_pickup_on = last_pickup_on_record(db, student)
    db.add(
        AuditLog(at=now, staff_id=staff.id, action="fixed_picked_up_to_no_show", student_id=student.id, booking_id=booking.id)
    )
    db.flush()
    return booking


def last_pickup_on_record(db: Session, student: Student) -> date | None:
    """The day of the student's last pickup still in the database: a booked bag or a walk-in."""
    booked = db.scalar(
        select(func.max(PickupDay.pickup_date))
        .join(Booking, Booking.pickup_day_id == PickupDay.id)
        .where(Booking.student_id == student.id, Booking.status == "picked_up")
    )
    walked_in = db.scalar(
        select(func.max(PickupDay.pickup_date))
        .join(WalkIn, WalkIn.pickup_day_id == PickupDay.id)
        .where(WalkIn.student_id == student.id)
    )
    return max((d for d in [booked, walked_in] if d is not None), default=None)


def _start_fix(db: Session, booking_id: int, status: str, now: datetime) -> tuple[Booking, PickupDay]:
    found = db.get(Booking, booking_id)
    if found is None:
        raise NotFound("There's no bag with that number.")
    _lock_student(db, found.student_id)
    booking = _lock_booking(db, booking_id)
    day = db.get(PickupDay, booking.pickup_day_id)
    if now >= day.no_show_at and booking.status in FIXABLE and booking.status != status:
        # Usually someone else fixed it a moment ago.
        said = "picked up" if booking.status == "picked_up" else "a no-show"
        raise CantFix(f"Bag {booking.code} is {said} already.")
    reason = why_not_fix(booking, day, now)
    if reason is not None:
        raise Problem(reason)
    return booking, day


# ---------- what the fix page lists ----------


def days_to_fix(db: Session, now: datetime) -> list[PickupDay]:
    """Pickup days that are over and still have bags on record, newest first."""
    return list(
        db.scalars(
            select(PickupDay)
            .where(
                PickupDay.no_show_at <= now,
                select(Booking.id)
                .where(Booking.pickup_day_id == PickupDay.id, Booking.status.in_(FIXABLE))
                .exists(),
            )
            .order_by(PickupDay.pickup_date.desc())
        )
    )


def bags_to_fix(db: Session, day: PickupDay) -> list[tuple[Booking, Slot]]:
    """The day's no-shows and picked-up bags, by time."""
    return list(
        db.execute(
            select(Booking, Slot)
            .join(Slot, Slot.id == Booking.slot_id)
            .where(Booking.pickup_day_id == day.id, Booking.status.in_(FIXABLE))
            .order_by(Slot.starts_at, Booking.code)
        )
    )


def next_booking_opens(db: Session, day: PickupDay, now: datetime) -> datetime | None:
    """When booking opens for the next pickup day after this one, if that's still to come.

    Fixes should be made before then, so the stock count and the pickup gap are
    right in time (B6).
    """
    opens = db.scalar(
        select(func.min(PickupDay.booking_opens_at)).where(
            PickupDay.pickup_date > day.pickup_date, PickupDay.closed_at.is_(None)
        )
    )
    return opens if opens is not None and opens > now else None


# ---------- shared ----------


def _contents(db: Session, booking: Booking) -> list[packing.InTheBag]:
    return packing.bag_contents(packing.food_in(db, booking), packing.substitutes_of(db, booking))


def _lock_student(db: Session, student_id: int) -> None:
    db.scalar(select(Student).where(Student.id == student_id).with_for_update().execution_options(populate_existing=True))


def _lock_booking(db: Session, booking_id: int) -> Booking:
    return db.scalar(
        select(Booking).where(Booking.id == booking_id).with_for_update().execution_options(populate_existing=True)
    )


def _lock_food(db: Session, variety_ids: set[int]) -> None:
    """Lock the food, lowest id first, and read the stock again."""
    if not variety_ids:
        return
    db.scalars(
        select(Variety)
        .where(Variety.id.in_(sorted(variety_ids)))
        .order_by(Variety.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
