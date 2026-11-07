"""The counter: handing over a packed bag, walk-ins, extras, and choices for gaps
(P5, B2, B3, E3, E4, F1, U6, W1, W3, W4).

Plain Python with a database session, like the other services. The routes in
app/routes/counter.py commit.

The counter is open on a pickup day from when booking closes (the bags are
being packed) until the no-show time. Two lines run side by side (W3): booked
bags are handed over by their code, and walk-ins are served from the shelf.

Locks, in the same order everywhere: the student, then the slot, then the hold
or booking, then the food from the lowest id up. Online booking takes the
student's lock too (services/booking.py). So a walk-in and an online booking
for the same student, at the same moment, can't both get past the pickup gap.
"""

import hmac
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Booking,
    CounterItem,
    Item,
    PickupDay,
    Settings,
    Slot,
    Staff,
    Student,
    Variety,
    WalkIn,
)
from app.problems import NotFound, Problem
from app.security.keyed_hash import id_hash
from app.services import accounts, packing
from app.services import booking as booking_rules
from app.services.booking import Choice, TimeTaken
from app.services.pickup_days import NEWFOUNDLAND, say_clock, say_day
from app.services.settings import food_bank_settings


class NotPackedYet(Problem):
    """Only a packed bag can be picked up (B2). The page links to the bag's packing page."""

    status_code = 409


class AlreadyPickedUp(Problem):
    status_code = 409


class BookingToCancel(Problem):
    """W4: serving this walk-in cancels their booking for a later day. The page asks first."""

    status_code = 409


# ---------- which day, and when ----------


def counter_day(db: Session, now: datetime) -> PickupDay | None:
    """Today's pickup day, in Newfoundland, if today is one."""
    today = now.astimezone(NEWFOUNDLAND).date()
    return db.scalar(select(PickupDay).where(PickupDay.pickup_date == today))


def why_counter_closed(db: Session, day: PickupDay | None, now: datetime) -> str | None:
    """Why nobody can be served right now, in words. None if the counter is open."""
    if day is None:
        today = now.astimezone(NEWFOUNDLAND).date()
        upcoming = db.scalar(
            select(PickupDay.pickup_date)
            .where(PickupDay.pickup_date > today, PickupDay.closed_at.is_(None))
            .order_by(PickupDay.pickup_date)
            .limit(1)
        )
        return "Today isn't a pickup day." + (f" The next one is {say_day(upcoming)}." if upcoming else "")
    if day.closed_at is not None:
        return f"{say_day(day.pickup_date)} is closed: {day.closed_reason}"
    if now < day.booking_closes_at:
        # No full stop: the time ends in "p.m." already.
        return f"The counter opens when booking closes, at {say_clock(day.booking_closes_at)}"
    if now >= day.no_show_at:
        return f"Pickup for {say_day(day.pickup_date)} is over."
    return None


def _open_day(db: Session, now: datetime) -> PickupDay:
    day = counter_day(db, now)
    reason = why_counter_closed(db, day, now)
    if reason is not None:
        raise Problem(reason)
    return day


# ---------- food from the shelf, within the same limits as booking (I3, I4, E3, U6) ----------


def _look_up(db: Session, variety_ids: list[int]) -> dict[int, tuple[Variety, Item]]:
    rows = db.execute(select(Variety, Item).join(Item, Item.id == Variety.item_id).where(Variety.id.in_(variety_ids)))
    return {variety.id: (variety, item) for variety, item in rows}


def _check_shelf_food(
    db: Session,
    choices: list[Choice],
    extras: list[int],
    in_bag: Counter[int],
    room: int,
    too_many: str,
    settings: Settings,
) -> dict[int, tuple[Variety, Item]]:
    """Food taken from the shelf at the counter: the limits that don't need the stock.

    in_bag counts what the student already has of each item, by item id.
    room is how many more things they can take, and too_many says why not.
    The stock is checked later, with the food locked.
    """
    chosen_ids = [choice.variety_id for choice in choices]
    if len(set(chosen_ids)) != len(chosen_ids) or len(set(extras)) != len(extras):
        raise Problem("Each kind of food can be listed once.")
    if any(choice.quantity < 1 for choice in choices):
        raise Problem("Choose at least 1 of each thing on the list.")
    found = _look_up(db, chosen_ids + extras)
    if any(variety_id not in found for variety_id in chosen_ids + extras):
        raise NotFound("Some of that food isn't on the list any more. Please reload the page.")

    for variety_id in chosen_ids + extras:
        variety, item = found[variety_id]
        if not variety.active:
            raise Problem(f"{variety.name} isn't on the list any more.")
    if sum(choice.quantity for choice in choices) > room:
        raise Problem(too_many)
    counts = Counter(in_bag)
    for choice in choices:
        variety, item = found[choice.variety_id]
        if item.is_extra:
            raise Problem(f"{item.name} is an extra: add it under Extras.")
        counts[item.id] += choice.quantity
        if counts[item.id] > settings.max_per_item:
            limit = settings.max_per_item
            raise Problem(f"{item.name}: {limit} at most, counting all its kinds together.")

    # E3: one variety of each extra item, like one bread. The database keeps this too.
    extra_items: set[int] = set()
    for variety_id in extras:
        variety, item = found[variety_id]
        if not item.is_extra:
            raise Problem(f"{variety.name} isn't an extra.")
        if item.id in extra_items:
            raise Problem(f"One {item.name} only: extras are one of each.")
        extra_items.add(item.id)
    return found


def _lock_food(db: Session, variety_ids: set[int]) -> None:
    """Lock the food, lowest id first, and read the stock again."""
    db.scalars(
        select(Variety)
        .where(Variety.id.in_(sorted(variety_ids)))
        .order_by(Variety.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()


def _take_from_shelf(
    db: Session,
    found: dict[int, tuple[Variety, Item]],
    choices: list[Choice],
    extras: list[int],
    booking: Booking | None = None,
    walk_in: WalkIn | None = None,
) -> None:
    """Take the food off stock (I4) and record it, for a booking or a walk-in. The food must be locked."""
    for variety_id, quantity in [(c.variety_id, c.quantity) for c in choices] + [(e, 1) for e in extras]:
        variety, item = found[variety_id]
        if variety.stock < quantity:
            raise TimeTaken(f"There's no {variety.name} left. Choose something else.")
        variety.stock -= quantity
        db.add(
            CounterItem(
                booking_id=booking.id if booking else None,
                walk_in_id=walk_in.id if walk_in else None,
                variety_id=variety.id,
                item_id=item.id,
                is_extra=item.is_extra,
                quantity=quantity,
            )
        )


def _lock_student(db: Session, student_id: int) -> Student:
    return db.scalar(
        select(Student).where(Student.id == student_id).with_for_update().execution_options(populate_existing=True)
    )


def _picked_up_on(student: Student, day: PickupDay) -> None:
    """The date the pickup gap counts from (F1). Kept on the account, so it covers
    walk-ins and outlives booking details deleted after the retention period (P7)."""
    if student.last_pickup_on is None or student.last_pickup_on < day.pickup_date:
        student.last_pickup_on = day.pickup_date


# ---------- handing over a booked bag (P5, B2, B3, U6) ----------


def find_bag(db: Session, code: str, now: datetime) -> Booking:
    """Today's bag with this code. The student says the code at the counter (P4)."""
    return _bag_by_code(db, _open_day(db, now), code)


def _bag_by_code(db: Session, day: PickupDay, code: str) -> Booking:
    code = code.strip().upper()
    booking = db.scalar(select(Booking).where(Booking.pickup_day_id == day.id, Booking.code == code))
    if booking is None:
        raise NotFound(f"There's no bag {code} today. Check the code with the student.")
    return booking


def why_not_hand_over(booking: Booking) -> Problem | None:
    """Only a packed bag can be picked up (B2)."""
    if booking.status == "picked_up":
        # No full stop: the time ends in "p.m." already.
        return AlreadyPickedUp(f"Bag {booking.code} was picked up already, at {say_clock(booking.picked_up_at)}")
    if booking.status == "booked":
        return NotPackedYet(f"Bag {booking.code} isn't packed yet. Pack it on the Packing page, then hand it over.")
    if booking.status == "cancelled":
        return Problem(f"Booking {booking.code} was cancelled, so there's no bag to hand over.")
    if booking.status == "no_show":
        return Problem(f"Booking {booking.code} is a no-show.")
    return None


def hand_over(
    db: Session,
    code: str,
    id_number: str,
    choices: list[Choice],
    extras: list[int],
    staff: Staff,
    now: datetime,
) -> Booking:
    """The volunteer hands over a packed bag, in one transaction (P5, B3).

    1. Find today's bag by its code, then lock the student and the booking.
    2. It must be packed (B2), and the card must match the booking (P5).
    3. If the bag is short, the student fills the gaps from the shelf, within
       the same limits (U6). Extras are one of each (E3).
    4. Lock that food, lowest id first, and take it off stock.
    5. Picked up, by this volunteer (B3). The pickup gap counts from today (F1).
    """
    settings = food_bank_settings(db)
    day = _open_day(db, now)
    found_bag = _bag_by_code(db, day, code)

    # 1. The student first, then the booking.
    student = _lock_student(db, found_bag.student_id)
    booking = db.scalar(
        select(Booking).where(Booking.id == found_bag.id).with_for_update().execution_options(populate_existing=True)
    )

    # 2.
    problem = why_not_hand_over(booking)
    if problem is not None:
        raise problem
    # P5: booking online doesn't prove anything. The card does.
    if not hmac.compare_digest(student.id_hash, id_hash(id_number)):
        raise Problem(
            f"That card doesn't match bag {booking.code}. Check the code and the card. "
            "Don't hand over the bag until they match."
        )

    # 3.
    food, substitutes = packing.food_in(db, booking), packing.substitutes_of(db, booking)
    in_bag: Counter[int] = Counter()
    for thing in packing.bag_contents(food, substitutes):
        in_bag[thing.item.id] += thing.quantity
    short = len(packing.gaps(food, substitutes))
    too_many = (
        "The bag isn't short, so there's nothing to choose from the shelf. Extras go under Extras."
        if short == 0
        else f"The bag is {short} short, so they can choose {short} thing{'s' if short > 1 else ''} from the shelf."
    )
    found = _check_shelf_food(db, choices, extras, in_bag, short, too_many, settings)

    # 4.
    _lock_food(db, set(found))
    _take_from_shelf(db, found, choices, extras, booking=booking)

    # 5.
    booking.status = "picked_up"
    booking.picked_up_at = now
    booking.picked_up_by_staff_id = staff.id
    _picked_up_on(student, day)
    db.add(AuditLog(at=now, staff_id=staff.id, action="marked_picked_up", student_id=student.id, booking_id=booking.id))
    db.flush()
    return booking


# ---------- walk-ins (W1, W3, W4) ----------


@dataclass
class WalkInCheck:
    can_serve: bool
    # Why not, in words, like "Not yet. Their next pickup can be on Tuesday, November 10 or later."
    why_not: str | None
    # No account for this card yet: recording the walk-in makes one.
    new_account: bool
    # W4: their booking for a later day, which serving them now cancels.
    cancels: Booking | None = None
    cancels_on: date | None = None


def _why_not_walk_in(
    db: Session, student: Student, day: PickupDay, settings: Settings
) -> tuple[str | None, Booking | None]:
    """Why this student can't be served as a walk-in today, and any booking it would cancel.

    The pickup gap has no exception (decided 7 Nov): one pickup every 28 days, however they come.
    """
    allowed_on = booking_rules.next_pickup_allowed_on(db, student, settings)
    if allowed_on is not None and day.pickup_date < allowed_on:
        return f"Not yet. Their next pickup can be on {say_day(allowed_on)} or later.", None
    upcoming = booking_rules.upcoming_booking(db, student)
    if upcoming is not None and upcoming.pickup_day_id == day.id:
        slot = db.get(Slot, upcoming.slot_id)
        # No full stop after the time: it ends in "p.m." already.
        return (
            f"They booked for today: bag {upcoming.code}, at {say_clock(slot.starts_at)} Hand over that bag instead.",
            None,
        )
    return None, upcoming


def check_walk_in(db: Session, id_number: str, now: datetime) -> WalkInCheck:
    """Can this card be served as a walk-in now? Saves nothing."""
    settings = food_bank_settings(db)
    day = _open_day(db, now)
    student = db.scalar(select(Student).where(Student.id_hash == id_hash(id_number)))
    if student is None:
        return WalkInCheck(can_serve=True, why_not=None, new_account=True)
    reason, upcoming = _why_not_walk_in(db, student, day, settings)
    if reason is not None:
        return WalkInCheck(can_serve=False, why_not=reason, new_account=False)
    cancels_on = db.get(PickupDay, upcoming.pickup_day_id).pickup_date if upcoming else None
    return WalkInCheck(can_serve=True, why_not=None, new_account=False, cancels=upcoming, cancels_on=cancels_on)


@dataclass
class RecordedWalkIn:
    walk_in: WalkIn
    new_account: bool
    cancelled: Booking | None
    next_pickup_on: date


def record_walk_in(
    db: Session,
    id_number: str,
    food: list[Choice],
    extras: list[int],
    cancel_booking: bool,
    staff: Staff,
    now: datetime,
) -> RecordedWalkIn:
    """A walk-in took this food from the shelf, in one transaction (W1, W4).

    1. Find the student by their card, or make their account (a first visit).
       Lock them.
    2. The pickup gap, with no exception. A booking for today means they get
       that bag instead.
    3. A booking for a later day is cancelled, if the volunteer said so (W4).
    4. The food: the same limits as booking, extras one of each.
    5. Lock all the food, lowest id first: the cancelled booking's goes back,
       then the walk-in's comes off.
    6. Record the walk-in. The pickup gap counts from today (F1).
    """
    settings = food_bank_settings(db)
    day = _open_day(db, now)

    # 1.
    hashed = id_hash(id_number)
    student = db.scalar(select(Student).where(Student.id_hash == hashed).with_for_update())
    new_account = student is None
    if student is None:
        student = Student(id_hash=hashed, created_at=now, created_by_staff_id=staff.id)
        db.add(student)
        db.flush()
        accounts.log(db, staff, "created_student", now, student=student)

    # 2.
    reason, upcoming = _why_not_walk_in(db, student, day, settings)
    if reason is not None:
        raise Problem(reason)

    # 3. Locks: the student is held, then the slot, then the booking.
    returned: list[packing.InTheBag] = []
    if upcoming is not None:
        upcoming_day = db.get(PickupDay, upcoming.pickup_day_id)
        if not cancel_booking:
            raise BookingToCancel(
                f"They have a booking for {say_day(upcoming_day.pickup_date)} (bag {upcoming.code}). "
                "Serving them now cancels it."
            )
        slot = db.scalar(select(Slot).where(Slot.id == upcoming.slot_id).with_for_update())
        upcoming = db.scalar(
            select(Booking).where(Booking.id == upcoming.id).with_for_update().execution_options(populate_existing=True)
        )
        if upcoming.status not in booking_rules.UPCOMING:
            # The student cancelled it online while we waited for the lock: nothing to cancel.
            upcoming = None
        else:
            returned = packing.bag_contents(packing.food_in(db, upcoming), packing.substitutes_of(db, upcoming))

    # 4.
    if not food and not extras:
        raise Problem("Choose what they took.")
    found = _check_shelf_food(
        db, food, extras, Counter(), settings.item_limit, f"A walk-in can take up to {settings.item_limit} things.", settings
    )

    # 5.
    _lock_food(db, set(found) | {thing.variety.id for thing in returned})
    if upcoming is not None:
        for thing in returned:
            thing.variety.stock += thing.quantity
        slot.booked_count -= 1
        upcoming.status = "cancelled"
        upcoming.cancelled_at = now
        upcoming.cancel_reason = "walk_in"
    walk_in = WalkIn(student_id=student.id, pickup_day_id=day.id, served_at=now, served_by_staff_id=staff.id)
    db.add(walk_in)
    db.flush()
    _take_from_shelf(db, found, food, extras, walk_in=walk_in)

    # 6.
    _picked_up_on(student, day)
    db.add(AuditLog(at=now, staff_id=staff.id, action="recorded_walk_in", student_id=student.id))
    db.flush()
    next_pickup_on = booking_rules.next_pickup_allowed_on(db, student, settings)
    return RecordedWalkIn(walk_in=walk_in, new_account=new_account, cancelled=upcoming, next_pickup_on=next_pickup_on)


# ---------- what the counter can hand out today ----------


@dataclass
class ShelfLine:
    variety: Variety
    item: Item


def on_the_shelf(db: Session) -> list[ShelfLine]:
    """Food with some left that nobody booked, A to Z, extras too. Hidden food is left out."""
    rows = db.execute(
        select(Variety, Item)
        .join(Item, Item.id == Variety.item_id)
        .where(Variety.active, Variety.stock > 0)
        .order_by(Item.name, Variety.name)
    )
    return [ShelfLine(variety, item) for variety, item in rows]
