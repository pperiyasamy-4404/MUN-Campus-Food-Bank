"""The counter, for staff: handing over a booked bag, and walk-ins (P5, B3, E3, U6, W1, W4).

ID numbers only ever come in the body of a POST, never in a web address (P10).
Answers never include the student's hash or anything about them (P4).
"""

from datetime import date, datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.deps import DB, CurrentStaff, Now
from app.models import Booking, CounterItem, Item, PickupDay, Slot, Staff, Student, Variety
from app.security.inputs import IdNumber
from app.services import booking as booking_rules
from app.services import counter, packing
from app.services.booking import Choice
from app.services.photos import photo_urls
from app.services.pickup_days import NEWFOUNDLAND
from app.services.settings import food_bank_settings

router = APIRouter(prefix="/api")


def _newfoundland(moment: datetime | None) -> datetime | None:
    return moment.astimezone(NEWFOUNDLAND) if moment else None


# ---------- what the counter can hand out today ----------


class ShelfFood(BaseModel):
    variety_id: int
    variety: str
    item_id: int
    item: str
    photo_url: str | None
    # Left that nobody booked.
    stock: int


class CounterLimits(BaseModel):
    item_limit: int
    max_per_item: int


class CounterPage(BaseModel):
    pickup_date: date | None
    is_open: bool
    # Why not, in words, like "Today isn't a pickup day. The next one is Monday, November 9."
    why_not: str | None
    # Walk-ins only during pickup hours (W3), like "Walk-ins are served from 3:30 p.m. to 5:30 p.m., ..."
    walk_ins_open: bool
    walk_ins_why_not: str | None
    limits: CounterLimits
    food: list[ShelfFood]
    # One of each extra item (E3).
    extras: list[ShelfFood]


@router.get("/counter")
def counter_page(staff: CurrentStaff, db: DB, now: Now) -> CounterPage:
    settings = food_bank_settings(db)
    day = counter.counter_day(db, now)
    why_not = counter.why_counter_closed(db, day, now)
    walk_ins_why_not = counter.why_walk_ins_closed(db, day, now)
    shelf = counter.on_the_shelf(db)
    urls = photo_urls(db, list({line.item.id for line in shelf}))

    def out(line: counter.ShelfLine) -> ShelfFood:
        return ShelfFood(
            variety_id=line.variety.id,
            variety=line.variety.name,
            item_id=line.item.id,
            item=line.item.name,
            photo_url=urls.get(line.item.id),
            stock=line.variety.stock,
        )

    return CounterPage(
        pickup_date=day.pickup_date if day else None,
        is_open=why_not is None,
        why_not=why_not,
        walk_ins_open=walk_ins_why_not is None,
        walk_ins_why_not=walk_ins_why_not,
        limits=CounterLimits(item_limit=settings.item_limit, max_per_item=settings.max_per_item),
        food=[out(line) for line in shelf if not line.item.is_extra],
        extras=[out(line) for line in shelf if line.item.is_extra],
    )


# ---------- handing over a booked bag ----------


class BagCode(BaseModel):
    # What the student says, like K3P.
    code: str = Field(min_length=1, max_length=10)


class InBag(BaseModel):
    variety: str
    item_id: int
    item: str
    quantity: int


class GivenAtCounter(BaseModel):
    variety: str
    item: str
    quantity: int
    is_extra: bool


class BagAtCounter(BaseModel):
    id: int
    code: str
    starts_at: datetime
    status: str
    # Why it can't be handed over, like "Bag K3P isn't packed yet...".
    why_not: str | None
    packed_by: str | None
    picked_up_at: datetime | None
    picked_up_by: str | None
    contents: list[InBag]
    sticky_note: list[str]
    # Things the substitutes couldn't replace. The student chooses these from the shelf (U6).
    short: int
    # Once picked up: what they chose from the shelf, and their extras.
    given_at_counter: list[GivenAtCounter]


def bag_at_counter(booking: Booking, db: DB) -> BagAtCounter:
    food, substitutes = packing.food_in(db, booking), packing.substitutes_of(db, booking)
    problem = counter.why_not_hand_over(booking)
    packer = db.get(Staff, booking.packed_by_staff_id) if booking.packed_by_staff_id else None
    giver = db.get(Staff, booking.picked_up_by_staff_id) if booking.picked_up_by_staff_id else None
    return BagAtCounter(
        id=booking.id,
        code=booking.code,
        starts_at=_newfoundland(db.get(Slot, booking.slot_id).starts_at),
        status=booking.status,
        why_not=problem.message if problem else None,
        packed_by=packer.username if packer else None,
        picked_up_at=_newfoundland(booking.picked_up_at),
        picked_up_by=giver.username if giver else None,
        contents=[
            InBag(variety=thing.variety.name, item_id=thing.item.id, item=thing.item.name, quantity=thing.quantity)
            for thing in packing.bag_contents(food, substitutes)
        ],
        sticky_note=packing.saved_note(food, substitutes),
        short=len(packing.gaps(food, substitutes)),
        given_at_counter=[
            GivenAtCounter(variety=variety.name, item=item.name, quantity=row.quantity, is_extra=row.is_extra)
            for row, variety, item in db.execute(
                select(CounterItem, Variety, Item)
                .join(Variety, Variety.id == CounterItem.variety_id)
                .join(Item, Item.id == CounterItem.item_id)
                .where(CounterItem.booking_id == booking.id)
                .order_by(CounterItem.is_extra, Item.name)
            )
        ],
    )


@router.post("/counter/find")
def find_a_bag(details: BagCode, staff: CurrentStaff, db: DB, now: Now) -> BagAtCounter:
    """The bag for the code the student says. A POST, so codes don't end up in the browser's history."""
    return bag_at_counter(counter.find_bag(db, details.code, now), db)


class ChoiceIn(BaseModel):
    variety_id: int
    quantity: int = Field(default=1, ge=1, le=99)


class HandOver(BaseModel):
    code: str = Field(min_length=1, max_length=10)
    # The number on the student's MUN card, checked against the booking (P5).
    id_number: IdNumber
    # What they chose from the shelf for the gaps (U6).
    choices: list[ChoiceIn] = Field(default=[], max_length=100)
    # Extras, by variety id: one of each extra item (E3).
    extras: list[int] = Field(default=[], max_length=100)


class HandedOver(BaseModel):
    code: str
    picked_up_at: datetime
    # The pickup gap counts from today (F1).
    next_pickup_on: date


@router.post("/counter/pickups", status_code=201)
def hand_over(details: HandOver, staff: CurrentStaff, db: DB, now: Now) -> HandedOver:
    booking = counter.hand_over(
        db,
        details.code,
        details.id_number.get_secret_value(),
        [Choice(choice.variety_id, choice.quantity) for choice in details.choices],
        details.extras,
        staff,
        now,
    )
    db.commit()
    student = db.get(Student, booking.student_id)
    return HandedOver(
        code=booking.code,
        picked_up_at=_newfoundland(booking.picked_up_at),
        next_pickup_on=booking_rules.next_pickup_allowed_on(db, student, food_bank_settings(db)),
    )


# ---------- walk-ins ----------


class Card(BaseModel):
    id_number: IdNumber


class BookingToCancelOut(BaseModel):
    pickup_date: date
    code: str


class WalkInCheckOut(BaseModel):
    can_serve: bool
    why_not: str | None
    # No account for this card yet: recording the walk-in makes one.
    new_account: bool
    # W4: their booking for a later day, which serving them now cancels.
    cancels: BookingToCancelOut | None


@router.post("/walk-ins/check")
def check_a_walk_in(details: Card, staff: CurrentStaff, db: DB, now: Now) -> WalkInCheckOut:
    """Can this card be served now? Saves nothing."""
    checked = counter.check_walk_in(db, details.id_number.get_secret_value(), now)
    return WalkInCheckOut(
        can_serve=checked.can_serve,
        why_not=checked.why_not,
        new_account=checked.new_account,
        cancels=BookingToCancelOut(pickup_date=checked.cancels_on, code=checked.cancels.code) if checked.cancels else None,
    )


class WalkInIn(BaseModel):
    id_number: IdNumber
    food: list[ChoiceIn] = Field(default=[], max_length=100)
    extras: list[int] = Field(default=[], max_length=100)
    # W4: yes, cancel their booking for a later day and serve them now.
    cancel_booking: bool = False


class WalkInDone(BaseModel):
    served_at: datetime
    things: int
    extras: int
    new_account: bool
    cancelled: BookingToCancelOut | None
    next_pickup_on: date


@router.post("/walk-ins", status_code=201)
def record_a_walk_in(details: WalkInIn, staff: CurrentStaff, db: DB, now: Now) -> WalkInDone:
    recorded = counter.record_walk_in(
        db,
        details.id_number.get_secret_value(),
        [Choice(choice.variety_id, choice.quantity) for choice in details.food],
        details.extras,
        details.cancel_booking,
        staff,
        now,
    )
    db.commit()
    cancelled = None
    if recorded.cancelled is not None:
        cancelled_day = db.get(PickupDay, recorded.cancelled.pickup_day_id)
        cancelled = BookingToCancelOut(pickup_date=cancelled_day.pickup_date, code=recorded.cancelled.code)
    return WalkInDone(
        served_at=_newfoundland(recorded.walk_in.served_at),
        things=sum(choice.quantity for choice in details.food),
        extras=len(details.extras),
        new_account=recorded.new_account,
        cancelled=cancelled,
        next_pickup_on=recorded.next_pickup_on,
    )
