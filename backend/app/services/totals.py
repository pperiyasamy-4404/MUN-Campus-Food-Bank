"""Totals: what the pickups added up to (P7, P12).

Booking details are deleted after the retention period, 90 days with the
sample settings. Only totals are kept. A day's totals are worked out from its
details while they exist, and added to its week just before they're deleted
(services/retention.py), so each day is counted exactly once.

The coordinator's page (step 9) will show each week as the saved totals plus
the days still on record, with small numbers hidden (P12).
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Booking, CounterItem, PickupDay, WalkIn, WeeklyItemTotal, WeeklyTotal
from app.services import packing


@dataclass
class Totals:
    # Booked bags handed over.
    picked_up: int = 0
    walk_ins: int = 0
    no_shows: int = 0
    cancelled: int = 0
    # How many of each item went out, by item id: in bags, at the counter, and to walk-ins.
    given_out: Counter[int] = field(default_factory=Counter)


def week_of(on: date) -> date:
    """The Monday of the week a date is in."""
    return on - timedelta(days=on.weekday())


def day_totals(db: Session, day: PickupDay) -> Totals:
    """A pickup day's totals, worked out from its details.

    What went out: for a booked bag that was handed over, what was really in it
    (the booked food that was on the shelf, plus substitutes) and anything given
    at the counter with it. For a walk-in, what they took. A no-show or a
    cancelled booking gave nothing out.
    """
    totals = Totals()
    statuses = db.execute(
        select(Booking.status, func.count()).where(Booking.pickup_day_id == day.id).group_by(Booking.status)
    )
    for status, count in statuses:
        if status == "picked_up":
            totals.picked_up = count
        elif status == "no_show":
            totals.no_shows = count
        elif status == "cancelled":
            totals.cancelled = count

    picked_up = db.scalars(select(Booking).where(Booking.pickup_day_id == day.id, Booking.status == "picked_up"))
    for booking in picked_up:
        for thing in packing.bag_contents(packing.food_in(db, booking), packing.substitutes_of(db, booking)):
            totals.given_out[thing.item.id] += thing.quantity

    totals.walk_ins = db.scalar(select(func.count()).select_from(WalkIn).where(WalkIn.pickup_day_id == day.id))

    # At the counter: with a handed-over bag, or to a walk-in.
    at_counter = db.execute(
        select(CounterItem.item_id, func.sum(CounterItem.quantity))
        .outerjoin(Booking, Booking.id == CounterItem.booking_id)
        .outerjoin(WalkIn, WalkIn.id == CounterItem.walk_in_id)
        .where(
            ((Booking.pickup_day_id == day.id) & (Booking.status == "picked_up")) | (WalkIn.pickup_day_id == day.id)
        )
        .group_by(CounterItem.item_id)
    )
    for item_id, quantity in at_counter:
        totals.given_out[item_id] += quantity
    return totals


def add_to_week(db: Session, week_starts_on: date, totals: Totals) -> None:
    """Add a day's totals to its week, making the week's row if it's the first."""
    counts = {
        "picked_up": totals.picked_up,
        "walk_ins": totals.walk_ins,
        "no_shows": totals.no_shows,
        "cancelled": totals.cancelled,
    }
    new_week = insert(WeeklyTotal).values(week_starts_on=week_starts_on, **counts)
    db.execute(
        new_week.on_conflict_do_update(
            index_elements=[WeeklyTotal.week_starts_on],
            set_={name: getattr(WeeklyTotal, name) + getattr(new_week.excluded, name) for name in counts},
        )
    )
    for item_id, quantity in sorted(totals.given_out.items()):
        new_item = insert(WeeklyItemTotal).values(week_starts_on=week_starts_on, item_id=item_id, given_out=quantity)
        db.execute(
            new_item.on_conflict_do_update(
                index_elements=[WeeklyItemTotal.week_starts_on, WeeklyItemTotal.item_id],
                set_={"given_out": WeeklyItemTotal.given_out + new_item.excluded.given_out},
            )
        )
