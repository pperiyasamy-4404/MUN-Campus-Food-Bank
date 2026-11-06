"""Holding a slot, booking, and cancelling: the heart of the system (F1-F3, S2, S5-S8, I3-I7, U2, B4).

Plain Python with a database session, like the other services. The routes in
app/routes/booking.py commit. If any check here refuses, the route never
commits, so everything done so far in that request is undone.

The order locks are taken in, everywhere: the slot, then the student's hold or
booking, then varieties from the lowest id up. Two transactions that take locks
in the same order can't end up waiting for each other forever (a deadlock).
"""

import secrets
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Booking, BookingItem, BookingSubstitute, Hold, Item, PickupDay, Settings, Slot, Student, Variety
from app.problems import NotFound, Problem
from app.services.pickup_days import booking_status, say_day, say_moment
from app.services.settings import food_bank_settings

UPCOMING = ("booked", "packed")

# Booking codes look like K3P: letter, digit, letter. Easy to say out loud, and
# the pattern can't spell a word. No I, L or O, and no 0 or 1, to avoid mix-ups.
CODE_LETTERS = "ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_DIGITS = "23456789"


class TimeTaken(Problem):
    """The slot or the food went to someone else first."""

    status_code = 409


class AlreadyBooked(Problem):
    """Pressing Book twice: the second press finds the first booking (B4)."""

    status_code = 409


class HoldRanOut(Problem):
    """The held time ran out, or was let go: the student starts again from choosing a time (S8).

    410 means "gone", so the page can tell this apart from other refusals
    without reading the words.
    """

    status_code = 410


# ---------- who may book which day (F1, F2, S5, S6, S7) ----------


def next_pickup_allowed_on(db: Session, student: Student, settings: Settings) -> date | None:
    """The first date the pickup gap allows, or None if there's been no pickup (F1).

    Counted in Newfoundland calendar days: a pickup on Thursday 1 October allows
    Thursday 29 October with a 28-day gap. Cancellations never count (F3), and
    no-shows count only if the setting says so.
    """
    counted = ["picked_up", "no_show"] if settings.no_shows_count else ["picked_up"]
    last_booked = db.scalar(
        select(func.max(PickupDay.pickup_date))
        .join(Booking, Booking.pickup_day_id == PickupDay.id)
        .where(Booking.student_id == student.id, Booking.status.in_(counted))
    )
    # last_pickup_on also covers walk-ins, and outlives booking details (P7).
    last = max((d for d in [student.last_pickup_on, last_booked] if d is not None), default=None)
    return None if last is None else last + timedelta(days=settings.pickup_gap_days)


def upcoming_booking(db: Session, student: Student) -> Booking | None:
    return db.scalar(select(Booking).where(Booking.student_id == student.id, Booking.status.in_(UPCOMING)))


def why_not(db: Session, student: Student, day: PickupDay, settings: Settings, now: datetime) -> str | None:
    """Why this student can't book this day right now, in words. None if they can.

    Checked before a hold, and again when they press Book (S8).
    """
    status = booking_status(day, now)
    if status == "day_closed":
        return f"{say_day(day.pickup_date)} is closed: {day.closed_reason}"
    if status == "not_open_yet":
        # No full stop: the time ends in "p.m." already.
        return f"Booking for {say_day(day.pickup_date)} opens {say_moment(day.booking_opens_at)}"
    if status == "booking_over":
        return f"Booking for {say_day(day.pickup_date)} is over."

    that_day = db.scalar(select(Booking).where(Booking.student_id == student.id, Booking.pickup_day_id == day.id))
    if that_day is not None:
        # S6: otherwise cancelling and booking again would be a way to change the items (I7).
        if that_day.status == "cancelled" and that_day.cancel_reason == "student":
            return f"You cancelled your booking for {say_day(day.pickup_date)}, so it can't be booked again. You can book a later day."
        if that_day.status == "cancelled":
            return f"Your booking for {say_day(day.pickup_date)} was cancelled, so it can't be booked again. You can book a later day."
        return f"You already have a booking for {say_day(day.pickup_date)}."

    upcoming = upcoming_booking(db, student)
    if upcoming is not None:  # F2
        upcoming_day = db.get(PickupDay, upcoming.pickup_day_id)
        return f"You already have a booking, for {say_day(upcoming_day.pickup_date)}. You can book again after it."

    allowed_on = next_pickup_allowed_on(db, student, settings)
    if allowed_on is not None and day.pickup_date < allowed_on:  # F1
        return f"Your next pickup can be on {say_day(allowed_on)} or later."
    return None


# ---------- holding a slot (S8) ----------


def hold_slot(db: Session, student: Student, slot_id: int, now: datetime) -> Hold:
    """Keep a slot for the student while they choose food, for the hold time.

    One hold per student (the table's primary key): holding a new slot lets go
    of the old one. Holding the same slot again doesn't add time, or a student
    could keep a slot forever. Once it has run out they can hold it again, if
    nobody else took it.
    """
    settings = food_bank_settings(db)
    # The slot's row is locked, so two students can't both take the last place's hold.
    slot = db.scalar(select(Slot).where(Slot.id == slot_id).with_for_update())
    if slot is None:
        raise NotFound("There's no pickup time with that number.")
    day = db.get(PickupDay, slot.pickup_day_id)
    reason = why_not(db, student, day, settings, now)
    if reason is not None:
        raise Problem(reason)

    mine = db.get(Hold, student.id)
    if mine is not None and mine.slot_id == slot.id and mine.held_until > now:
        return mine

    others_holding = db.scalar(
        select(func.count())
        .select_from(Hold)
        .where(Hold.slot_id == slot.id, Hold.held_until > now, Hold.student_id != student.id)
    )
    if slot.booked_count + others_holding >= slot.capacity:
        raise TimeTaken("Someone else just took that time. Choose another one.")

    held_until = now + timedelta(minutes=settings.hold_minutes)
    if mine is None:
        mine = Hold(student_id=student.id, slot_id=slot.id, held_until=held_until)
        db.add(mine)
    else:
        mine.slot_id, mine.held_until = slot.id, held_until
    db.flush()
    return mine


def let_go(db: Session, student: Student) -> None:
    """The student chose to start over: their slot is free for others straight away."""
    db.execute(delete(Hold).where(Hold.student_id == student.id))


def places_held(db: Session, slot_ids: list[int], now: datetime) -> dict[int, int]:
    """For each slot, how many students are holding it right now."""
    rows = db.execute(
        select(Hold.slot_id, func.count())
        .where(Hold.slot_id.in_(slot_ids), Hold.held_until > now)
        .group_by(Hold.slot_id)
    )
    return {slot_id: count for slot_id, count in rows}


# ---------- pressing Book ----------


@dataclass
class Choice:
    variety_id: int
    quantity: int = 1


def book(db: Session, student: Student, items: list[Choice], substitutes: list[int], now: datetime) -> Booking:
    """Turn the student's hold into a booking, in one transaction (tables.html, part 6).

    1. Lock the slot, then check the hold is still theirs and hasn't run out.
    2. Check the rules again: the day, the pickup gap, other bookings (S8).
    3. Check the food: the limits (I3) and the substitutes (U2).
    4. Take a place in the slot: the database refuses going over capacity (S2).
    5. Take the food off stock, lowest id first (I4, I5).
    6. Save the booking, its food and substitutes, and let go of the hold.
    """
    settings = food_bank_settings(db)

    # 1. Which slot does the hold say? Lock that slot first, then read the hold again.
    held = db.get(Hold, student.id)
    if held is None:
        raise _no_hold(db, student)
    slot = db.scalar(select(Slot).where(Slot.id == held.slot_id).with_for_update())
    hold = db.scalar(
        select(Hold).where(Hold.student_id == student.id).with_for_update().execution_options(populate_existing=True)
    )
    # A second press of Book waited for the lock above. By now the first press
    # has booked and let go of the hold.
    if hold is None or hold.slot_id != slot.id:
        raise _no_hold(db, student)
    if hold.held_until <= now:
        raise HoldRanOut(f"Your {settings.hold_minutes} minutes ran out, so the time was let go. Choose a time again.")

    # 2. The rules, again: something may have changed while they chose.
    day = db.get(PickupDay, slot.pickup_day_id)
    reason = why_not(db, student, day, settings, now)
    if reason is not None:
        raise Problem(reason)

    # 3. The food.
    _check_food(db, items, substitutes, settings)

    # 4. A place in the slot. The hold kept it free, and the database rule is the safety net.
    slot.booked_count += 1

    # 5. The food off stock, lowest id first, each row locked.
    for choice in sorted(items, key=lambda choice: choice.variety_id):
        variety = db.scalar(
            select(Variety)
            .where(Variety.id == choice.variety_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if variety.stock < choice.quantity:
            raise TimeTaken(f"Sorry, {variety.name} has just run out. Choose something else.")
        variety.stock -= choice.quantity

    # 6. Save it all.
    booking = Booking(
        student_id=student.id,
        pickup_day_id=day.id,
        slot_id=slot.id,
        code=_new_code(db, day),
        status="booked",
        booked_at=now,
    )
    db.add(booking)
    db.flush()
    db.add_all(BookingItem(booking_id=booking.id, variety_id=c.variety_id, quantity=c.quantity) for c in items)
    db.add_all(
        BookingSubstitute(booking_id=booking.id, rank=rank, variety_id=variety_id)
        for rank, variety_id in enumerate(substitutes, start=1)
    )
    db.delete(hold)
    db.flush()
    return booking


def _no_hold(db: Session, student: Student) -> Problem:
    upcoming = upcoming_booking(db, student)
    if upcoming is not None:
        return AlreadyBooked(f"You're booked already. Your code is {upcoming.code}.")
    return HoldRanOut("Choose a pickup time first.")


def _check_food(db: Session, items: list[Choice], substitutes: list[int], settings: Settings) -> None:
    """The limits that need settings or other tables, so the code checks them (I3, U2)."""
    if not items:
        raise Problem("Choose at least one thing.")
    chosen_ids = [choice.variety_id for choice in items]
    if len(set(chosen_ids)) != len(chosen_ids):
        raise Problem("Each kind of food can be listed once.")
    if any(choice.quantity < 1 for choice in items):
        raise Problem("Choose at least 1 of each thing on your list.")
    if len(substitutes) > settings.substitute_limit:
        raise Problem(f"You can list up to {settings.substitute_limit} substitutes.")
    if len(set(substitutes)) != len(substitutes):
        raise Problem("Each substitute can be listed once.")
    if set(substitutes) & set(chosen_ids):
        raise Problem("A substitute can't be something already on your list.")

    rows = db.execute(
        select(Variety, Item).join(Item, Item.id == Variety.item_id).where(Variety.id.in_(chosen_ids + substitutes))
    ).all()
    found = {variety.id: (variety, item) for variety, item in rows}
    for variety_id in chosen_ids + substitutes:
        if variety_id not in found:
            raise NotFound("Some of that food isn't on the list any more. Please reload the page.")
        variety, item = found[variety_id]
        if not variety.active:
            raise Problem(f"{variety.name} isn't on the list any more. Choose something else.")
        if item.is_extra:
            raise Problem(f"{item.name} is an extra: ask for it at pickup instead.")  # E1, U2

    total = sum(choice.quantity for choice in items)
    if total > settings.item_limit:
        raise Problem(f"You can choose up to {settings.item_limit} things. Your list has {total}.")
    per_item: Counter[int] = Counter()
    for choice in items:
        per_item[found[choice.variety_id][1].id] += choice.quantity
    for item_id, count in per_item.items():
        if count > settings.max_per_item:
            name = next(item.name for _, item in found.values() if item.id == item_id)
            limit = settings.max_per_item
            raise Problem(f"You can choose {limit} {name} at most, counting all its kinds together.")


def _new_code(db: Session, day: PickupDay) -> str:
    """A code nobody else has on this day. The database's unique rule is the safety net."""
    taken = set(db.scalars(select(Booking.code).where(Booking.pickup_day_id == day.id)))
    while True:
        code = secrets.choice(CODE_LETTERS) + secrets.choice(CODE_DIGITS) + secrets.choice(CODE_LETTERS)
        if code not in taken:
            return code


# ---------- cancelling (S6, I6) ----------


def cancel(db: Session, student: Student, now: datetime) -> Booking:
    """The student cancels their upcoming booking, until booking closes (S6).

    The place and the food go straight back for someone else. The student can't
    book that day again, but can book a later one: cancellations don't count
    toward the pickup gap (F3).
    """
    found = upcoming_booking(db, student)
    if found is None:
        raise NotFound("You don't have a booking to cancel.")
    # Locks in the same order as booking: the slot, the booking, then the food.
    slot = db.scalar(select(Slot).where(Slot.id == found.slot_id).with_for_update())
    booking = db.scalar(
        select(Booking).where(Booking.id == found.id).with_for_update().execution_options(populate_existing=True)
    )
    if booking.status not in UPCOMING:
        raise NotFound("You don't have a booking to cancel.")
    day = db.get(PickupDay, booking.pickup_day_id)
    if now >= day.booking_closes_at:
        raise Problem(
            f"Cancelling closed at {say_moment(day.booking_closes_at)}, because the bags are being packed. "
            "If you can't come, please tell the food bank."
        )

    slot.booked_count -= 1
    booked = db.scalars(
        select(BookingItem).where(BookingItem.booking_id == booking.id).order_by(BookingItem.variety_id)
    ).all()
    for item in booked:
        variety = db.scalar(
            select(Variety).where(Variety.id == item.variety_id).with_for_update().execution_options(populate_existing=True)
        )
        variety.stock += item.quantity
    booking.status = "cancelled"
    booking.cancelled_at = now
    booking.cancel_reason = "student"
    db.flush()
    return booking
