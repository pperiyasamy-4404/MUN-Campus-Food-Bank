from datetime import date, datetime, time

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Identity,
    SmallInteger,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Settings that only make sense as 1 or more.
AT_LEAST_ONE = [
    "pickup_gap_days",
    "slot_minutes",
    "slot_capacity",
    "hold_minutes",
    "item_limit",
    "max_per_item",
    "setup_code_days",
    "login_tries",
    "login_window_minutes",
]


class Settings(Base):
    """The food bank's numbers, in one row the coordinator can change.

    Sample values are in CONSTRAINTS.md. Times of day are Newfoundland clock times.
    """

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=False, default=1, server_default=text("1")
    )
    pickup_gap_days: Mapped[int]
    slot_minutes: Mapped[int]
    slot_capacity: Mapped[int]
    hold_minutes: Mapped[int]
    item_limit: Mapped[int]
    max_per_item: Mapped[int]
    substitute_limit: Mapped[int]
    booking_opens_days_before: Mapped[int]
    booking_opens_time: Mapped[time]
    booking_closes_time: Mapped[time]
    no_show_time: Mapped[time]
    no_shows_count: Mapped[bool]
    retention_days: Mapped[int]
    setup_code_days: Mapped[int]
    login_tries: Mapped[int]
    login_window_minutes: Mapped[int]

    __table_args__ = (
        CheckConstraint("id = 1", name="only_one_row"),
        *(CheckConstraint(f"{column} >= 1", name=f"{column}_at_least_1") for column in AT_LEAST_ONE),
        CheckConstraint("substitute_limit >= 0", name="substitute_limit_not_negative"),
        CheckConstraint("booking_opens_days_before >= 0", name="booking_opens_days_before_not_negative"),
        CheckConstraint("max_per_item <= item_limit", name="max_per_item_within_item_limit"),
        # Never delete a pickup the pickup gap still needs. Also keeps retention at 1 or more.
        CheckConstraint("retention_days >= pickup_gap_days", name="retention_covers_pickup_gap"),
        CheckConstraint(
            "booking_opens_days_before >= 1 OR booking_opens_time < booking_closes_time",
            name="booking_opens_before_it_closes",
        ),
        CheckConstraint("no_show_time > booking_closes_time", name="no_show_after_booking_closes"),
    )


class PickupHours(Base):
    """The weekly pattern: which weekdays have pickups, and when (S1)."""

    __tablename__ = "pickup_hours"

    # 1 is Monday, 7 is Sunday. The primary key means each weekday appears once.
    weekday: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    starts_at: Mapped[time]
    ends_at: Mapped[time]

    __table_args__ = (
        CheckConstraint("weekday BETWEEN 1 AND 7", name="weekday_1_to_7"),
        CheckConstraint("ends_at > starts_at", name="ends_after_it_starts"),
    )


class PickupDay(Base):
    """One real pickup date, with its own booking times.

    The times are worked out from the settings when the day is made, then kept
    here. So the coordinator can move one day's times (S9) or close one day (S7),
    and changing the settings never moves a day students can already see.
    """

    __tablename__ = "pickup_days"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    pickup_date: Mapped[date] = mapped_column(unique=True)
    booking_opens_at: Mapped[datetime]
    booking_closes_at: Mapped[datetime]
    no_show_at: Mapped[datetime]
    closed_at: Mapped[datetime | None]
    closed_reason: Mapped[str | None]

    __table_args__ = (
        CheckConstraint("booking_opens_at < booking_closes_at", name="booking_opens_before_it_closes"),
        CheckConstraint("booking_closes_at < no_show_at", name="no_show_after_booking_closes"),
        # A closed day always says why, and a reason only goes with a closed day.
        CheckConstraint("(closed_at IS NULL) = (closed_reason IS NULL)", name="closed_has_a_reason"),
    )


class Slot(Base):
    """A 10-minute pickup slot.

    booked_count is like stock turned upside down: stock counts what's left and
    can't go below 0, booked_count counts what's taken and can't go above
    capacity. Booking adds 1, cancelling takes 1 away (S2).
    Holds aren't counted here: the code checks room for a hold with the slot locked.
    """

    __tablename__ = "slots"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    pickup_day_id: Mapped[int] = mapped_column(ForeignKey("pickup_days.id"))
    starts_at: Mapped[datetime]
    capacity: Mapped[int]
    booked_count: Mapped[int] = mapped_column(server_default=text("0"))

    __table_args__ = (
        CheckConstraint("capacity >= 1", name="capacity_at_least_1"),
        CheckConstraint("booked_count >= 0", name="booked_count_not_negative"),
        # Even when two students press Book on the last place at the same moment (S2).
        CheckConstraint("booked_count <= capacity", name="not_over_capacity"),
        UniqueConstraint("pickup_day_id", "starts_at"),
        # Lets a booking link to the pair (slot, day), so its day always matches its slot's.
        UniqueConstraint("id", "pickup_day_id"),
    )
