from datetime import date

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

WEEK_COUNTS = ["picked_up", "walk_ins", "no_shows", "cancelled"]


class WeeklyTotal(Base):
    """What one week's pickups added up to, kept after the details are deleted (P7).

    A pickup day's numbers are added here in the same transaction that deletes
    its details, so each day is counted exactly once. Until then, its numbers are
    worked out from the details themselves (services/totals.py). The coordinator
    sees totals by week, with small numbers hidden (P12, step 9).

    Only numbers: nothing here says which student came.
    """

    __tablename__ = "weekly_totals"

    # The Monday the week starts on, in Newfoundland.
    week_starts_on: Mapped[date] = mapped_column(primary_key=True)
    # Booked bags handed over.
    picked_up: Mapped[int]
    walk_ins: Mapped[int]
    no_shows: Mapped[int]
    cancelled: Mapped[int]

    __table_args__ = (
        CheckConstraint("EXTRACT(ISODOW FROM week_starts_on) = 1", name="week_starts_on_a_monday"),
        *(CheckConstraint(f"{column} >= 0", name=f"{column}_not_negative") for column in WEEK_COUNTS),
    )


class WeeklyItemTotal(Base):
    """How many of one item went out in one week: in bags, at the counter, and to walk-ins (P7).

    By item, not variety: "12 oats", whatever the kind.
    """

    __tablename__ = "weekly_item_totals"

    week_starts_on: Mapped[date] = mapped_column(ForeignKey("weekly_totals.week_starts_on"), primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), primary_key=True)
    given_out: Mapped[int]

    __table_args__ = (CheckConstraint("given_out >= 1", name="given_out_at_least_1"),)
