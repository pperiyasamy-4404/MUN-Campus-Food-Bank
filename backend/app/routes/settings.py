"""The Settings page, for the coordinator (R3): the food bank's numbers and the weekly pickup hours.

The rules about what fits together are in app/services/settings.py. Here,
each number is checked on its own, with a message for its own box.
"""

from datetime import datetime, time
from typing import Annotated, Any

from fastapi import APIRouter
from pydantic import BaseModel, BeforeValidator
from pydantic_core import PydanticCustomError
from sqlalchemy import select

from app.deps import DB, CurrentCoordinator, Now
from app.models import AuditLog, PickupDay, Staff
from app.services import settings as rules
from app.services.pickup_days import DAYS_AHEAD, NEWFOUNDLAND

router = APIRouter(prefix="/api")


# ---------- what comes in ----------


def whole_number(low: int, high: int):
    """A whole number in a range, typed in a box: 28, or "28". The highest numbers
    are there to catch a slip, like 2800 for 28."""

    def check(typed: Any) -> int:
        try:
            number = int(str(typed).strip()) if not isinstance(typed, bool) else None
        except ValueError:
            number = None
        if number is None or not low <= number <= high:
            raise PydanticCustomError("whole_number", f"Enter a whole number from {low} to {high}.")
        return number

    return Annotated[int, BeforeValidator(check)]


def _clock(typed: Any) -> time:
    """A time of day, like "15:30". Seconds are dropped."""
    try:
        clock = typed if isinstance(typed, time) else time.fromisoformat(str(typed).strip())
    except ValueError:
        raise PydanticCustomError("clock", "Enter a time, like 3:30 PM.") from None
    if clock.tzinfo is not None:
        raise PydanticCustomError("clock", "Enter a time without a time zone: times are St. John's time.")
    return clock.replace(second=0, microsecond=0)


Clock = Annotated[time, BeforeValidator(_clock)]


class HoursIn(BaseModel):
    weekday: whole_number(1, 7)
    starts_at: Clock
    ends_at: Clock


class SettingsIn(BaseModel):
    pickup_gap_days: whole_number(1, 365)
    slot_minutes: whole_number(5, 120)
    slot_capacity: whole_number(1, 50)
    hold_minutes: whole_number(1, 60)
    item_limit: whole_number(1, 100)
    max_per_item: whole_number(1, 100)
    substitute_limit: whole_number(0, 20)
    booking_opens_days_before: whole_number(0, rules.MOST_DAYS_BEFORE)
    booking_opens_time: Clock
    booking_closes_time: Clock
    no_show_time: Clock
    no_shows_count: bool
    retention_days: whole_number(1, 3650)
    setup_code_days: whole_number(1, 60)
    login_tries: whole_number(1, 100)
    login_window_minutes: whole_number(1, 1440)
    pickup_hours: list[HoursIn]


# ---------- what goes out ----------


class HoursOut(BaseModel):
    weekday: int
    # "15:30": what a time box in the browser takes.
    starts_at: str
    ends_at: str


class SettingsOut(BaseModel):
    pickup_gap_days: int
    slot_minutes: int
    slot_capacity: int
    hold_minutes: int
    item_limit: int
    max_per_item: int
    substitute_limit: int
    booking_opens_days_before: int
    booking_opens_time: str
    booking_closes_time: str
    no_show_time: str
    no_shows_count: bool
    retention_days: int
    setup_code_days: int
    login_tries: int
    login_window_minutes: int
    pickup_hours: list[HoursOut]


class SettingsPage(BaseModel):
    settings: SettingsOut
    # Days already made, from tomorrow. They keep their own times.
    days_made: list[str]
    # How far ahead days are made: 7.
    days_ahead: int
    # After saving: days already made that got the new number of students per slot.
    capacity_changed_on: list[str] = []
    # When the settings were last changed, and by whom.
    changed_at: datetime | None
    changed_by: str | None


def _hhmm(clock: time) -> str:
    return f"{clock:%H:%M}"


def settings_page(db: DB, now: datetime) -> SettingsPage:
    current = rules.food_bank_settings(db)
    values = {name: getattr(current, name) for name in rules.SETTING_NAMES}
    for name in ("booking_opens_time", "booking_closes_time", "no_show_time"):
        values[name] = _hhmm(values[name])
    today = now.astimezone(NEWFOUNDLAND).date()
    made = db.scalars(select(PickupDay.pickup_date).where(PickupDay.pickup_date > today).order_by(PickupDay.pickup_date))
    last_change = db.execute(
        select(AuditLog.at, Staff.username)
        .join(Staff, Staff.id == AuditLog.staff_id)
        .where(AuditLog.action == "changed_settings")
        .order_by(AuditLog.at.desc())
        .limit(1)
    ).first()
    return SettingsPage(
        settings=SettingsOut(
            **values,
            pickup_hours=[
                HoursOut(weekday=day.weekday, starts_at=_hhmm(day.starts_at), ends_at=_hhmm(day.ends_at))
                for day in rules.weekly_hours(db)
            ],
        ),
        days_made=[on.isoformat() for on in made],
        days_ahead=DAYS_AHEAD.days,
        changed_at=last_change.at.astimezone(NEWFOUNDLAND) if last_change else None,
        changed_by=last_change.username if last_change else None,
    )


# ---------- the addresses ----------


@router.get("/settings")
def get_settings(coordinator: CurrentCoordinator, db: DB, now: Now) -> SettingsPage:
    return settings_page(db, now)


@router.put("/settings")
def change_settings(new: SettingsIn, coordinator: CurrentCoordinator, db: DB, now: Now) -> SettingsPage:
    """Save every setting at once. New pickup days use them; days already made keep their times,
    except students per slot, which also reaches days whose booking hasn't opened."""
    values = new.model_dump(exclude={"pickup_hours"})
    hours = [rules.WeeklyHours(day.weekday, day.starts_at, day.ends_at) for day in new.pickup_hours]
    changed_on = rules.change_settings(db, values, hours, coordinator, now)
    db.commit()
    page = settings_page(db, now)
    page.capacity_changed_on = [on.isoformat() for on in changed_on]
    return page
