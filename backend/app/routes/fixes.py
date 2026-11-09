"""Fixing a pickup marked wrong, after the day is over, for staff (B6).

A bag handed over but not marked: no-show -> picked up. A bag marked picked up
that the student never took: picked up -> no-show. Every fix is logged with who
made it. The rules are in app/services/no_shows.py.

Answers never include anything about the student, only the bag's code (P4).
"""

from datetime import date, datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.deps import DB, CurrentStaff, Now
from app.models import Booking, PickupDay, Slot, Staff
from app.problems import NotFound
from app.services import no_shows
from app.services.pickup_days import NEWFOUNDLAND

router = APIRouter(prefix="/api")


class FixBag(BaseModel):
    id: int
    code: str
    starts_at: datetime
    # "no_show" or "picked_up"
    status: str
    picked_up_at: datetime | None
    picked_up_by: str | None
    # Why it can't be fixed, like "Bag K3P was never packed, so it can't have been handed over."
    why_not: str | None


class FixPage(BaseModel):
    # Pickup days that are over and still have bags on record, newest first.
    days: list[date]
    # The day shown: the one asked for, or the newest.
    day: date | None
    # When booking opens for the next pickup day, if that's still to come. Fix before then (B6).
    fix_before: datetime | None
    bags: list[FixBag]


def _bag_out(db: DB, booking: Booking, slot: Slot, day: PickupDay, now: datetime) -> FixBag:
    giver = db.get(Staff, booking.picked_up_by_staff_id) if booking.picked_up_by_staff_id else None
    return FixBag(
        id=booking.id,
        code=booking.code,
        starts_at=slot.starts_at.astimezone(NEWFOUNDLAND),
        status=booking.status,
        picked_up_at=booking.picked_up_at.astimezone(NEWFOUNDLAND) if booking.picked_up_at else None,
        picked_up_by=giver.username if giver else None,
        why_not=no_shows.why_not_fix(booking, day, now),
    )


@router.get("/fixes")
def fix_page(staff: CurrentStaff, db: DB, now: Now, day: date | None = None) -> FixPage:
    days = no_shows.days_to_fix(db, now)
    shown = next((d for d in days if d.pickup_date == day), None) if day else (days[0] if days else None)
    if day is not None and shown is None:
        raise NotFound("There's nothing to fix on that day.")
    if shown is None:
        return FixPage(days=[], day=None, fix_before=None, bags=[])
    opens = no_shows.next_booking_opens(db, shown, now)
    return FixPage(
        days=[d.pickup_date for d in days],
        day=shown.pickup_date,
        fix_before=opens.astimezone(NEWFOUNDLAND) if opens else None,
        bags=[_bag_out(db, booking, slot, shown, now) for booking, slot in no_shows.bags_to_fix(db, shown)],
    )


def _fixed(db: DB, booking_id: int, now: datetime) -> FixBag:
    booking, slot = db.execute(
        select(Booking, Slot).join(Slot, Slot.id == Booking.slot_id).where(Booking.id == booking_id)
    ).one()
    return _bag_out(db, booking, slot, db.get(PickupDay, booking.pickup_day_id), now)


@router.post("/fixes/{booking_id}/picked-up")
def fix_to_picked_up(booking_id: int, staff: CurrentStaff, db: DB, now: Now) -> FixBag:
    """It was handed over, but nobody pressed Hand over: no-show -> picked up."""
    no_shows.fix_to_picked_up(db, booking_id, staff, now)
    db.commit()
    return _fixed(db, booking_id, now)


@router.post("/fixes/{booking_id}/no-show")
def fix_to_no_show(booking_id: int, staff: CurrentStaff, db: DB, now: Now) -> FixBag:
    """It was marked picked up, but the student never took it: picked up -> no-show."""
    no_shows.fix_to_no_show(db, booking_id, staff, now)
    db.commit()
    return _fixed(db, booking_id, now)
