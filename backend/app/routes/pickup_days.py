"""The upcoming pickup days and their slots. Read only: nothing here changes the database."""

from collections import defaultdict
from datetime import date, datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.deps import DB, Now
from app.models import PickupDay, Slot
from app.services.booking import places_held
from app.services.pickup_days import NEWFOUNDLAND, BookingStatus, booking_status

router = APIRouter(prefix="/api")


class SlotOut(BaseModel):
    id: int
    starts_at: datetime
    # Places not booked and not held by a student who is choosing food right now.
    places_left: int


class PickupDayOut(BaseModel):
    pickup_date: date
    booking_opens_at: datetime
    booking_closes_at: datetime
    booking_status: BookingStatus
    # Seconds until booking opens, by the server's clock, for the page's countdown.
    # 0 once it has opened. The page counts down from this, not from the phone's
    # own clock, which may be wrong (13 Nov).
    seconds_until_booking_opens: int
    closed_reason: str | None
    slots: list[SlotOut]


@router.get("/pickup-days")
def upcoming_pickup_days(db: DB, now: Now) -> list[PickupDayOut]:
    """Today's pickup day, if there is one, and every one after it.

    Times go out in Newfoundland time, like 2026-11-09T15:30:00-03:30 (T1).
    Places left counts bookings and holds that haven't run out (S8).
    """
    today = now.astimezone(NEWFOUNDLAND).date()
    days = db.scalars(
        select(PickupDay).where(PickupDay.pickup_date >= today).order_by(PickupDay.pickup_date)
    ).all()

    # One query for all the slots, not one per day.
    slots_by_day: dict[int, list[SlotOut]] = defaultdict(list)
    slots = db.scalars(
        select(Slot).where(Slot.pickup_day_id.in_([day.id for day in days])).order_by(Slot.starts_at)
    ).all()
    held = places_held(db, [slot.id for slot in slots], now)
    for slot in slots:
        slots_by_day[slot.pickup_day_id].append(
            SlotOut(
                id=slot.id,
                starts_at=slot.starts_at.astimezone(NEWFOUNDLAND),
                places_left=max(0, slot.capacity - slot.booked_count - held.get(slot.id, 0)),
            )
        )

    return [
        PickupDayOut(
            pickup_date=day.pickup_date,
            booking_opens_at=day.booking_opens_at.astimezone(NEWFOUNDLAND),
            booking_closes_at=day.booking_closes_at.astimezone(NEWFOUNDLAND),
            booking_status=booking_status(day, now),
            seconds_until_booking_opens=max(0, int((day.booking_opens_at - now).total_seconds())),
            closed_reason=day.closed_reason,
            slots=slots_by_day[day.id],
        )
        for day in days
    ]
