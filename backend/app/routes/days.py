"""The coordinator's pickup days: close a day (S7), open it again, move its booking times (S9).

The rules are in app/services/day_changes.py. Only the coordinator can use
these (R3). A date in the address, like /api/coordinator/days/2026-11-23,
says nothing about anyone.
"""

from datetime import date, datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.deps import DB, CurrentCoordinator, Now
from app.models import Booking, PickupDay, PickupHours
from app.services import day_changes
from app.services.booking import UPCOMING
from app.services.pickup_days import NEWFOUNDLAND, BookingStatus, booking_status

router = APIRouter(prefix="/api/coordinator")


# ---------- what goes out ----------


class DayRow(BaseModel):
    pickup_date: date
    booking_opens_at: datetime
    booking_closes_at: datetime
    pickup_starts_at: datetime
    pickup_ends_at: datetime
    no_show_at: datetime
    booking_status: BookingStatus
    closed_reason: str | None
    # Bookings still to come, and how many of them are packed.
    booked: int
    packed: int
    # Why each change can't be made, in words. None if it can.
    why_not_close: str | None
    why_not_reopen: str | None
    why_not_move: str | None


class DaysPage(BaseModel):
    # Days not over yet, from today.
    days: list[DayRow]
    # 1 is Monday. A later date on one of these can be closed ahead of time.
    pickup_weekdays: list[int]
    # The furthest date that can be closed.
    close_until: date


def _local(moment: datetime) -> datetime:
    return moment.astimezone(NEWFOUNDLAND)


def day_row(db: DB, day: PickupDay, counts: dict[str, int], now: datetime) -> DayRow:
    return DayRow(
        pickup_date=day.pickup_date,
        booking_opens_at=_local(day.booking_opens_at),
        booking_closes_at=_local(day.booking_closes_at),
        pickup_starts_at=_local(day.pickup_starts_at),
        pickup_ends_at=_local(day.pickup_ends_at),
        no_show_at=_local(day.no_show_at),
        booking_status=booking_status(day, now),
        closed_reason=day.closed_reason,
        booked=counts.get("booked", 0) + counts.get("packed", 0),
        packed=counts.get("packed", 0),
        why_not_close=day_changes.why_not_close(day, now),
        why_not_reopen=day_changes.why_not_reopen(db, day, now) if day.closed_at else None,
        why_not_move=day_changes.why_not_move(day, now),
    )


def _counts(db: DB, day_ids: list[int]) -> dict[int, dict[str, int]]:
    counts: dict[int, dict[str, int]] = {day_id: {} for day_id in day_ids}
    rows = db.execute(
        select(Booking.pickup_day_id, Booking.status, func.count())
        .where(Booking.pickup_day_id.in_(day_ids), Booking.status.in_(UPCOMING))
        .group_by(Booking.pickup_day_id, Booking.status)
    )
    for day_id, status, count in rows:
        counts[day_id][status] = count
    return counts


def _one_row(db: DB, pickup_date: date, now: datetime) -> DayRow:
    day = db.scalar(select(PickupDay).where(PickupDay.pickup_date == pickup_date))
    return day_row(db, day, _counts(db, [day.id])[day.id], now)


# ---------- the addresses ----------


@router.get("/days")
def days_page(coordinator: CurrentCoordinator, db: DB, now: Now) -> DaysPage:
    days = db.scalars(select(PickupDay).where(PickupDay.no_show_at > now).order_by(PickupDay.pickup_date)).all()
    counts = _counts(db, [day.id for day in days])
    return DaysPage(
        days=[day_row(db, day, counts[day.id], now) for day in days],
        pickup_weekdays=list(db.scalars(select(PickupHours.weekday).order_by(PickupHours.weekday))),
        close_until=now.astimezone(NEWFOUNDLAND).date() + day_changes.FURTHEST_AHEAD,
    )


class CloseIn(BaseModel):
    # Students see it: "Monday, November 23 is closed: Snow storm."
    reason: str


class ClosedOut(BaseModel):
    day: DayRow
    cancelled: int
    were_packed: int


@router.post("/days/{pickup_date}/close")
def close_day(pickup_date: date, details: CloseIn, coordinator: CurrentCoordinator, db: DB, now: Now) -> ClosedOut:
    """Close the day and cancel its bookings (S7). A later date not made yet is made, then closed."""
    closed = day_changes.close_day(db, pickup_date, details.reason, coordinator, now)
    db.commit()
    return ClosedOut(day=_one_row(db, pickup_date, now), cancelled=closed.cancelled, were_packed=closed.were_packed)


@router.post("/days/{pickup_date}/reopen")
def reopen_day(pickup_date: date, coordinator: CurrentCoordinator, db: DB, now: Now) -> DayRow:
    day_changes.reopen_day(db, pickup_date, coordinator, now)
    db.commit()
    return _one_row(db, pickup_date, now)


class BookingTimesIn(BaseModel):
    # St. John's time, as a date-and-time box in the browser gives it: "2026-11-22T19:00".
    opens_at: datetime
    closes_at: datetime


def _in_newfoundland(moment: datetime) -> datetime:
    """A time typed without a time zone is St. John's time (T1)."""
    return moment.replace(tzinfo=NEWFOUNDLAND) if moment.tzinfo is None else moment


@router.put("/days/{pickup_date}/booking-times")
def move_booking_times(
    pickup_date: date, times: BookingTimesIn, coordinator: CurrentCoordinator, db: DB, now: Now
) -> DayRow:
    """Move when booking opens and closes for this day only (S9)."""
    day_changes.move_booking_times(
        db, pickup_date, _in_newfoundland(times.opens_at), _in_newfoundland(times.closes_at), coordinator, now
    )
    db.commit()
    return _one_row(db, pickup_date, now)
