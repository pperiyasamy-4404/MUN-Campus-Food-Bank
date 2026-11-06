"""A student's booking: hold a time, book food, see it, cancel it (S5-S8, I3-I7, U2).

Every address here is the logged-in student's own: none takes a booking id, so
nobody can look at or cancel someone else's booking by changing a number.
"""

from datetime import date, datetime

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.deps import DB, CurrentStudent, Now
from app.models import Booking, BookingItem, BookingSubstitute, Hold, Item, PickupDay, Slot, Variety
from app.services import booking as booking_rules
from app.services.pickup_days import NEWFOUNDLAND
from app.services.settings import food_bank_settings

router = APIRouter(prefix="/api")


# ---------- what goes out ----------


class Limits(BaseModel):
    item_limit: int
    max_per_item: int
    substitute_limit: int
    hold_minutes: int


class HoldOut(BaseModel):
    slot_id: int
    pickup_date: date
    starts_at: datetime
    held_until: datetime
    # Counted by the server, so a phone with its clock wrong still counts down right.
    seconds_left: int


class FoodLine(BaseModel):
    variety: str
    item: str
    quantity: int


class SubstituteLine(BaseModel):
    rank: int
    variety: str
    item: str


class BookingOut(BaseModel):
    # What the student says at the counter. Volunteers see this, never the ID number (P4).
    code: str
    status: str
    pickup_date: date
    starts_at: datetime
    booked_at: datetime
    # Cancelling is allowed until booking closes (S6).
    cancel_until: datetime
    can_cancel: bool
    items: list[FoodLine]
    substitutes: list[SubstituteLine]


class MyBooking(BaseModel):
    limits: Limits
    booking: BookingOut | None
    hold: HoldOut | None
    # The first date the pickup gap allows, if there's been a pickup (F1).
    next_pickup_allowed_on: date | None


def hold_out(hold: Hold, db: DB, now: datetime) -> HoldOut:
    slot = db.get(Slot, hold.slot_id)
    day = db.get(PickupDay, slot.pickup_day_id)
    return HoldOut(
        slot_id=slot.id,
        pickup_date=day.pickup_date,
        starts_at=slot.starts_at.astimezone(NEWFOUNDLAND),
        held_until=hold.held_until.astimezone(NEWFOUNDLAND),
        seconds_left=max(0, int((hold.held_until - now).total_seconds())),
    )


def booking_out(booking: Booking, db: DB, now: datetime) -> BookingOut:
    slot = db.get(Slot, booking.slot_id)
    day = db.get(PickupDay, booking.pickup_day_id)
    items = db.execute(
        select(Variety.name, Item.name, BookingItem.quantity)
        .join(Variety, Variety.id == BookingItem.variety_id)
        .join(Item, Item.id == Variety.item_id)
        .where(BookingItem.booking_id == booking.id)
        .order_by(Item.name, Variety.name)
    ).all()
    substitutes = db.execute(
        select(BookingSubstitute.rank, Variety.name, Item.name)
        .join(Variety, Variety.id == BookingSubstitute.variety_id)
        .join(Item, Item.id == Variety.item_id)
        .where(BookingSubstitute.booking_id == booking.id)
        .order_by(BookingSubstitute.rank)
    ).all()
    return BookingOut(
        code=booking.code,
        status=booking.status,
        pickup_date=day.pickup_date,
        starts_at=slot.starts_at.astimezone(NEWFOUNDLAND),
        booked_at=booking.booked_at.astimezone(NEWFOUNDLAND),
        cancel_until=day.booking_closes_at.astimezone(NEWFOUNDLAND),
        can_cancel=booking.status in booking_rules.UPCOMING and now < day.booking_closes_at,
        items=[FoodLine(variety=variety, item=item, quantity=quantity) for variety, item, quantity in items],
        substitutes=[SubstituteLine(rank=rank, variety=variety, item=item) for rank, variety, item in substitutes],
    )


@router.get("/my-booking")
def my_booking(student: CurrentStudent, db: DB, now: Now) -> MyBooking:
    """Everything the booking page needs about this student. The days and food are
    at /api/pickup-days and /api/food, the same for everyone."""
    settings = food_bank_settings(db)
    upcoming = booking_rules.upcoming_booking(db, student)
    hold = db.get(Hold, student.id)
    return MyBooking(
        limits=Limits(
            item_limit=settings.item_limit,
            max_per_item=settings.max_per_item,
            substitute_limit=settings.substitute_limit,
            hold_minutes=settings.hold_minutes,
        ),
        booking=booking_out(upcoming, db, now) if upcoming else None,
        hold=hold_out(hold, db, now) if hold is not None and hold.held_until > now else None,
        next_pickup_allowed_on=booking_rules.next_pickup_allowed_on(db, student, settings),
    )


# ---------- holding a time ----------


class HoldIn(BaseModel):
    slot_id: int


@router.post("/holds", status_code=201)
def hold_a_time(details: HoldIn, student: CurrentStudent, db: DB, now: Now) -> HoldOut:
    hold = booking_rules.hold_slot(db, student, details.slot_id, now)
    db.commit()
    return hold_out(hold, db, now)


@router.delete("/holds", status_code=204)
def let_go(student: CurrentStudent, db: DB) -> Response:
    booking_rules.let_go(db, student)
    db.commit()
    return Response(status_code=204)


# ---------- booking ----------


class ChoiceIn(BaseModel):
    variety_id: int
    quantity: int = Field(default=1, ge=1, le=99)


class BookingIn(BaseModel):
    items: list[ChoiceIn] = Field(max_length=100)
    # Variety ids, best first.
    substitutes: list[int] = Field(default=[], max_length=100)


@router.post("/bookings", status_code=201)
def book(details: BookingIn, student: CurrentStudent, db: DB, now: Now) -> BookingOut:
    choices = [booking_rules.Choice(choice.variety_id, choice.quantity) for choice in details.items]
    booking = booking_rules.book(db, student, choices, details.substitutes, now)
    db.commit()
    return booking_out(booking, db, now)


@router.post("/my-booking/cancel", status_code=204)
def cancel(student: CurrentStudent, db: DB, now: Now) -> Response:
    booking_rules.cancel(db, student, now)
    db.commit()
    return Response(status_code=204)
