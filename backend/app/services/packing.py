"""Packing the bags: the packing queue, the refill rule, Packed, and undoing it (K1, U4, U5, U7, U8, B2).

Plain Python with a database session, like the other services. The routes in
app/routes/packing.py commit.

How a volunteer packs one bag:
1. They open it from the queue and put in the booked food, tapping "Picked" as
   each thing goes in. Picked is only on the page: the server never sees it.
2. For food that isn't on the shelf, they tap "Out of stock". Each tap asks
   plan() what goes in instead, and what to write on the sticky note. plan()
   saves nothing, so a wrong tap is simply tapped again.
3. They put in what it says, write the note, and press Packed. pack() works the
   plan out again with the food locked, and saves everything at once.

Locks, in the same order as booking and cancelling: the booking, then the food
from the lowest id up. Packing never needs the slot.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Booking,
    BookingItem,
    BookingSubstitute,
    Item,
    PickupDay,
    Settings,
    Slot,
    Staff,
    Variety,
)
from app.problems import NotFound, Problem
from app.services.pickup_days import say_clock, say_day
from app.services.settings import food_bank_settings


class AlreadyPacked(Problem):
    """Pressing Packed twice, or two volunteers packing the same bag: booked -> packed happens once (B2)."""

    status_code = 409


class PlanChanged(Problem):
    """What the volunteer was told to put in changed before they pressed Packed.

    Usually another bag took the last of a substitute. The page asks for the
    plan again and shows what to put in now.
    """

    status_code = 409


# ---------- which day, and when (K1) ----------


def packing_day(db: Session, now: datetime) -> PickupDay | None:
    """The pickup day volunteers are packing for, or will pack for next.

    The first day, not closed, whose no-show time hasn't passed: on a Monday,
    that's Monday until 6 pm, then Thursday.
    """
    return db.scalar(
        select(PickupDay)
        .where(PickupDay.no_show_at > now, PickupDay.closed_at.is_(None))
        .order_by(PickupDay.pickup_date)
        .limit(1)
    )


def why_not_pack(day: PickupDay, now: datetime) -> str | None:
    """Why bags for this day can't be packed right now, in words. None if they can (K1).

    Packing starts when booking closes. Until then students can still cancel,
    so the list isn't final. It goes on until the no-show time, not only until
    pickup starts, so a bag that's late can still be packed while the student waits.
    """
    if day.closed_at is not None:
        return f"{say_day(day.pickup_date)} is closed: {day.closed_reason}"
    if now < day.booking_closes_at:
        return (
            f"Packing for {say_day(day.pickup_date)} starts at {say_clock(day.booking_closes_at)}, "
            "when booking closes. Until then, students can still cancel."
        )
    if now >= day.no_show_at:
        return f"Pickup for {say_day(day.pickup_date)} is over."
    return None


# ---------- the refill rule (U4), with no database ----------

# What happens to one substitute:
#   use               it goes in the bag
#   not_on_shelf      the volunteer looked and found none
#   none_left         the stock says none are left that nobody else booked (U3)
#   already_has_item  it would give the student a second of that item, like a second oats
#   not_needed        the bag is full again, or nothing was missing
Outcome = Literal["use", "not_on_shelf", "none_left", "already_has_item", "not_needed"]


@dataclass(frozen=True)
class BookedFood:
    variety_id: int
    item_id: int
    quantity: int


@dataclass(frozen=True)
class SubstituteFood:
    rank: int
    variety_id: int
    item_id: int
    # At least one left that no other bag is waiting for, and not hidden.
    can_take: bool


@dataclass
class Refill:
    # What happens to each substitute, by variety id, best first.
    outcomes: dict[int, Outcome]
    # Each missing thing, in the order the volunteer marked them, with what
    # replaces it. None if nothing could: the student chooses at the counter (U6).
    swaps: list[tuple[int, int | None]]

    @property
    def used(self) -> list[int]:
        """The substitutes that go in the bag, best first."""
        return [variety_id for variety_id, outcome in self.outcomes.items() if outcome == "use"]


def refill(
    booked: list[BookedFood],
    missing: list[tuple[int, int]],
    substitutes: list[SubstituteFood],
    not_on_shelf: set[int],
    max_per_item: int,
) -> Refill:
    """Which substitutes go in the bag (U4).

    missing is (variety id, how many) for the booked food that wasn't on the
    shelf, in the order the volunteer found out. Missing food is replaced from
    the substitutes, best first. A substitute is skipped if there's none of it,
    or if it would give the student more of an item than the per-item limit
    (with the sample limit of 1: a second oats). Refilling stops when the bag
    is back to the size that was booked.

    Any substitute can fill any gap, so it doesn't matter which food went
    missing first. Each substitute fills one gap.
    """
    how_many_missing = dict(missing)
    in_bag: Counter[int] = Counter()
    for food in booked:
        in_bag[food.item_id] += food.quantity - how_many_missing.get(food.variety_id, 0)
    gaps = [variety_id for variety_id, how_many in missing for _ in range(how_many)]

    outcomes: dict[int, Outcome] = {}
    used: list[int] = []
    for substitute in sorted(substitutes, key=lambda substitute: substitute.rank):
        if substitute.variety_id in not_on_shelf:
            outcome: Outcome = "not_on_shelf"
        elif len(used) == len(gaps):
            outcome = "not_needed"
        elif not substitute.can_take:
            outcome = "none_left"
        elif in_bag[substitute.item_id] >= max_per_item:
            outcome = "already_has_item"
        else:
            outcome = "use"
            used.append(substitute.variety_id)
            in_bag[substitute.item_id] += 1
        outcomes[substitute.variety_id] = outcome

    swaps = [(gap, used[n] if n < len(used) else None) for n, gap in enumerate(gaps)]
    return Refill(outcomes=outcomes, swaps=swaps)


def sticky_note(swaps: list[tuple[int, int | None]], names: dict[int, str]) -> list[str]:
    """What to write on the sticky note on the bag (U8), like ["Sunflower oil → White rice"]."""
    return [
        f"{names[gap]} → {names[used]}" if used is not None else f"{names[gap]} → choose at the counter"
        for gap, used in swaps
    ]


# ---------- one bag, from the database ----------


@dataclass
class BagFood:
    row: BookingItem
    variety: Variety
    item: Item


@dataclass
class BagSubstitute:
    row: BookingSubstitute
    variety: Variety
    item: Item


@dataclass(frozen=True)
class Missing:
    """Booked food the volunteer didn't find on the shelf. how_many None means all of it."""

    variety_id: int
    how_many: int | None = None


@dataclass
class Plan:
    food: list[BagFood]
    substitutes: list[BagSubstitute]
    # (variety id, how many), checked, in the order the volunteer marked them.
    missing: list[tuple[int, int]]
    refill: Refill

    def names(self) -> dict[int, str]:
        return {line.variety.id: line.variety.name for line in [*self.food, *self.substitutes]}

    def sticky_note(self) -> list[str]:
        return sticky_note(self.refill.swaps, self.names())

    def booked(self) -> int:
        return sum(line.row.quantity for line in self.food)

    def in_bag(self) -> int:
        """Booked, minus the gaps nothing could fill."""
        return self.booked() - sum(1 for _, used in self.refill.swaps if used is None)


def find_bag(db: Session, booking_id: int) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise NotFound("There's no bag with that number.")
    return booking


def food_in(db: Session, booking: Booking) -> list[BagFood]:
    """The booked food, A to Z, the way it's shown on the bag's page."""
    rows = db.execute(
        select(BookingItem, Variety, Item)
        .join(Variety, Variety.id == BookingItem.variety_id)
        .join(Item, Item.id == Variety.item_id)
        .where(BookingItem.booking_id == booking.id)
        .order_by(func.lower(Item.name), func.lower(Variety.name))
    ).all()
    return [BagFood(row, variety, item) for row, variety, item in rows]


def substitutes_of(db: Session, booking: Booking) -> list[BagSubstitute]:
    """The substitutes, best first."""
    rows = db.execute(
        select(BookingSubstitute, Variety, Item)
        .join(Variety, Variety.id == BookingSubstitute.variety_id)
        .join(Item, Item.id == Variety.item_id)
        .where(BookingSubstitute.booking_id == booking.id)
        .order_by(BookingSubstitute.rank)
    ).all()
    return [BagSubstitute(row, variety, item) for row, variety, item in rows]


def why_not_this_bag(db: Session, booking: Booking, day: PickupDay, now: datetime) -> Problem | None:
    """Why this bag can't be packed right now, or None if it can."""
    if booking.status in ("packed", "picked_up"):
        packer = db.get(Staff, booking.packed_by_staff_id) if booking.packed_by_staff_id else None
        if packer is None or booking.packed_at is None:
            return AlreadyPacked(f"Bag {booking.code} is packed already.")
        # No full stop: the time ends in "p.m." already.
        return AlreadyPacked(f"Bag {booking.code} is packed already, by {packer.username} at {say_clock(booking.packed_at)}")
    if booking.status == "cancelled":
        return Problem(f"Booking {booking.code} was cancelled, so there's nothing to pack.")
    if booking.status != "booked":
        return Problem(f"Booking {booking.code} is a no-show, so there's nothing to pack.")
    reason = why_not_pack(day, now)
    return Problem(reason) if reason else None


def plan(db: Session, booking_id: int, missing: list[Missing], not_on_shelf: list[int], now: datetime) -> Plan:
    """What goes in the bag instead of the missing food, and the sticky note. Saves nothing."""
    booking = find_bag(db, booking_id)
    problem = why_not_this_bag(db, booking, db.get(PickupDay, booking.pickup_day_id), now)
    if problem is not None:
        raise problem
    return _plan(food_in(db, booking), substitutes_of(db, booking), missing, not_on_shelf, food_bank_settings(db))


def _plan(
    food: list[BagFood],
    substitutes: list[BagSubstitute],
    missing: list[Missing],
    not_on_shelf: list[int],
    settings: Settings,
) -> Plan:
    checked = _check_findings(food, substitutes, missing, not_on_shelf)
    result = refill(
        booked=[BookedFood(line.variety.id, line.item.id, line.row.quantity) for line in food],
        missing=checked,
        substitutes=[
            SubstituteFood(
                rank=line.row.rank,
                variety_id=line.variety.id,
                item_id=line.item.id,
                can_take=line.variety.active and line.variety.stock >= 1,
            )
            for line in substitutes
        ],
        not_on_shelf=set(not_on_shelf),
        max_per_item=settings.max_per_item,
    )
    return Plan(food=food, substitutes=substitutes, missing=checked, refill=result)


def _check_findings(
    food: list[BagFood], substitutes: list[BagSubstitute], missing: list[Missing], not_on_shelf: list[int]
) -> list[tuple[int, int]]:
    """Only this bag's own food can be missing, and only its own substitutes can go in (U5)."""
    booked = {line.variety.id: line for line in food}
    checked: list[tuple[int, int]] = []
    for found in missing:
        line = booked.get(found.variety_id)
        if line is None:
            raise Problem("Only food booked for this bag can be marked as missing.")
        if any(variety_id == found.variety_id for variety_id, _ in checked):
            raise Problem(f"{line.variety.name} is marked as missing twice.")
        how_many = line.row.quantity if found.how_many is None else found.how_many
        if not 1 <= how_many <= line.row.quantity:
            raise Problem(f"{line.variety.name}: {line.row.quantity} were booked, so 1 to {line.row.quantity} can be missing.")
        checked.append((found.variety_id, how_many))

    own_substitutes = {line.variety.id for line in substitutes}
    if any(variety_id not in own_substitutes for variety_id in not_on_shelf):
        raise Problem("Only this bag's substitutes can be marked as out of stock.")
    if len(set(not_on_shelf)) != len(not_on_shelf):
        raise Problem("Each substitute can be marked once.")
    return checked


# ---------- pressing Packed ----------


def pack(
    db: Session,
    booking_id: int,
    missing: list[Missing],
    not_on_shelf: list[int],
    uses: list[int],
    staff: Staff,
    now: datetime,
) -> Plan:
    """The bag is packed: save what went in it, in one transaction (U4, U7, B2).

    1. Lock the booking. A second press of Packed waits here, then finds it packed.
    2. Lock the food, lowest id first, and read the stock again.
    3. Work the plan out again. If it no longer matches what the volunteer was
       told to put in (`uses`), refuse, so the page can show the new plan.
    4. Save: what was missing, which substitute replaced what, and the stock.
       Food nobody found on the shelf can't be booked again until it's counted,
       and every other bag with it is flagged.
    """
    settings = food_bank_settings(db)

    # 1.
    booking = db.scalar(
        select(Booking).where(Booking.id == booking_id).with_for_update().execution_options(populate_existing=True)
    )
    if booking is None:
        raise NotFound("There's no bag with that number.")
    problem = why_not_this_bag(db, booking, db.get(PickupDay, booking.pickup_day_id), now)
    if problem is not None:
        raise problem

    # 2. ORDER BY id with FOR UPDATE locks the rows one by one in that order.
    food, substitutes = food_in(db, booking), substitutes_of(db, booking)
    variety_ids = sorted({line.variety.id for line in [*food, *substitutes]})
    db.scalars(
        select(Variety)
        .where(Variety.id.in_(variety_ids))
        .order_by(Variety.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()

    # 3.
    packed = _plan(food, substitutes, missing, not_on_shelf, settings)
    if packed.refill.used != list(uses):
        raise PlanChanged(
            "The substitutes changed while you packed: another bag may have taken the last one, "
            "or someone counted the shelf. Check the list again: it now says what to put in."
        )

    # 4.
    how_many_missing = dict(packed.missing)
    for line in food:
        line.row.missing = how_many_missing.get(line.variety.id, 0)
        if line.row.missing:
            _ran_out(line.variety, now)
    replaced = {used: gap for gap, used in packed.refill.swaps if used is not None}
    for line in substitutes:
        if line.variety.id in not_on_shelf:
            _ran_out(line.variety, now)
        if line.variety.id in replaced:
            # Substitutes weren't taken from stock when booking (U3). This one is now.
            line.variety.stock -= 1
            line.row.replaces_variety_id = replaced[line.variety.id]
    booking.status = "packed"
    booking.packed_at = now
    booking.packed_by_staff_id = staff.id
    db.flush()
    return packed


class NotPacked(Problem):
    """Undo Packed on a bag that isn't packed (any more), or was handed over already."""

    status_code = 409


def why_not_unpack(booking: Booking, day: PickupDay, now: datetime) -> Problem | None:
    """Why Packed can't be undone on this bag right now, or None if it can."""
    if booking.status == "picked_up":
        return NotPacked(f"Bag {booking.code} was picked up already, so Packed can't be undone.")
    if booking.status != "packed":
        return NotPacked(f"Bag {booking.code} isn't packed.")
    reason = why_not_pack(day, now)
    return Problem(reason) if reason else None


def unpack(db: Session, booking_id: int, staff: Staff, now: datetime) -> Booking:
    """Undo Packed, for a bag packed by mistake (decided 7 Nov: packed -> booked, before pickup).

    The bag goes back to "to pack". The substitutes that went in go back on the
    shelf, so their stock goes up again. The booked food stays promised to this
    student, so its stock doesn't change. "Ran out" marks stay: the shelf really
    had none. The undo is logged with who did it, like other fixes (B6).

    Locks in the same order as pack(): the booking, then the food from the lowest id up.
    """
    booking = db.scalar(
        select(Booking).where(Booking.id == booking_id).with_for_update().execution_options(populate_existing=True)
    )
    if booking is None:
        raise NotFound("There's no bag with that number.")
    problem = why_not_unpack(booking, db.get(PickupDay, booking.pickup_day_id), now)
    if problem is not None:
        raise problem

    food, substitutes = food_in(db, booking), substitutes_of(db, booking)
    used = sorted(line.variety.id for line in substitutes if line.row.replaces_variety_id is not None)
    db.scalars(
        select(Variety)
        .where(Variety.id.in_(used))
        .order_by(Variety.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    for line in substitutes:
        if line.row.replaces_variety_id is not None:
            line.variety.stock += 1
            line.row.replaces_variety_id = None
    for line in food:
        line.row.missing = 0
    booking.status = "booked"
    booking.packed_at = None
    booking.packed_by_staff_id = None
    db.add(AuditLog(at=now, staff_id=staff.id, action="undid_packed", booking_id=booking.id))
    db.flush()
    return booking


def _ran_out(variety: Variety, now: datetime) -> None:
    """Out of stock while packing: nobody else can book it, and every bag still waiting
    for it is flagged in the queue, until someone counts the shelf (U7)."""
    variety.stock = 0
    if variety.ran_out_at is None:
        variety.ran_out_at = now


@dataclass(frozen=True)
class InTheBag:
    variety: Variety
    item: Item
    quantity: int


def bag_contents(food: list[BagFood], substitutes: list[BagSubstitute]) -> list[InTheBag]:
    """What's really in a bag: the booked food, minus what wasn't on the shelf,
    plus the substitutes that went in.

    Before packing, that's simply what was booked. The counter uses it for the
    limits when a student fills a gap (U6). When a bag's food goes back on the
    shelf, this is what goes back.
    """
    contents = [
        InTheBag(line.variety, line.item, line.row.quantity - line.row.missing)
        for line in food
        if line.row.quantity > line.row.missing
    ]
    contents += [InTheBag(line.variety, line.item, 1) for line in substitutes if line.row.replaces_variety_id]
    return contents


def gaps(food: list[BagFood], substitutes: list[BagSubstitute]) -> list[int]:
    """The booked food nothing replaced, one entry per missing thing (U6)."""
    filled = Counter(line.row.replaces_variety_id for line in substitutes if line.row.replaces_variety_id)
    unfilled: list[int] = []
    for line in food:
        unfilled += [line.variety.id] * (line.row.missing - filled[line.variety.id])
    return unfilled


def saved_note(food: list[BagFood], substitutes: list[BagSubstitute]) -> list[str]:
    """The sticky note of a bag that's packed, from what was saved."""
    swaps: list[tuple[int, int | None]] = [
        (line.row.replaces_variety_id, line.variety.id) for line in substitutes if line.row.replaces_variety_id
    ]
    filled = Counter(gap for gap, _ in swaps)
    for line in food:
        swaps += [(line.variety.id, None)] * (line.row.missing - filled[line.variety.id])
    names = {line.variety.id: line.variety.name for line in [*food, *substitutes]}
    return sticky_note(swaps, names)


# ---------- the packing queue ----------


@dataclass
class QueueBag:
    booking: Booking
    starts_at: datetime
    # How many things were booked.
    things: int
    # Booked food a volunteer found none of in another bag. Only for bags still to pack (U7).
    ran_out: list[str]
    packed_by: str | None


def queue(db: Session, day: PickupDay) -> list[QueueBag]:
    """Every bag for the day, by pickup time. Cancelled bookings have no bag."""
    rows = db.execute(
        select(Booking, Slot.starts_at)
        .join(Slot, Slot.id == Booking.slot_id)
        .where(Booking.pickup_day_id == day.id, Booking.status != "cancelled")
        .order_by(Slot.starts_at, Booking.code)
    ).all()
    booking_ids = [booking.id for booking, _ in rows]

    things = dict(
        db.execute(
            select(BookingItem.booking_id, func.sum(BookingItem.quantity))
            .where(BookingItem.booking_id.in_(booking_ids))
            .group_by(BookingItem.booking_id)
        ).all()
    )
    ran_out: dict[int, list[str]] = defaultdict(list)
    for booking_id, name in db.execute(
        select(BookingItem.booking_id, Variety.name)
        .join(Variety, Variety.id == BookingItem.variety_id)
        .where(BookingItem.booking_id.in_(booking_ids), Variety.ran_out_at.is_not(None))
        .order_by(func.lower(Variety.name))
    ):
        ran_out[booking_id].append(name)
    packer_ids = {booking.packed_by_staff_id for booking, _ in rows if booking.packed_by_staff_id}
    packers = dict(db.execute(select(Staff.id, Staff.username).where(Staff.id.in_(packer_ids))).all())

    return [
        QueueBag(
            booking=booking,
            starts_at=starts_at,
            things=int(things.get(booking.id, 0)),
            ran_out=ran_out[booking.id] if booking.status == "booked" else [],
            packed_by=packers.get(booking.packed_by_staff_id),
        )
        for booking, starts_at in rows
    ]
