from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WalkIn(Base):
    """A student served without a booking, in their own line (W1, W3).

    It counts toward the pickup gap like a pickup: the student's last_pickup_on
    is set to the day. No slot, and nothing packed: they take what's on the
    shelf, recorded in counter_items.
    """

    __tablename__ = "walk_ins"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    pickup_day_id: Mapped[int] = mapped_column(ForeignKey("pickup_days.id"))
    served_at: Mapped[datetime]
    # Who recorded it (R4).
    served_by_staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"))

    __table_args__ = (
        # The pickup gap allows one pickup in 30 days, so one walk-in a day is the
        # least it can mean. The code checks the gap. This is the safety net.
        UniqueConstraint("student_id", "pickup_day_id"),
    )


class CounterItem(Base):
    """Food handed over at the counter that wasn't in a packed bag.

    - extras, at most one of each extra item (E3, E4)
    - what a student chose from the shelf for a gap no substitute could fill (U6)
    - everything a walk-in takes (W1)

    Each row belongs to one booking or one walk-in. The item and is_extra are
    copied onto the row, so the database itself can keep "one bread per
    student": two links make sure the copies can't be wrong.
    """

    __tablename__ = "counter_items"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"))
    walk_in_id: Mapped[int | None] = mapped_column(ForeignKey("walk_ins.id", ondelete="CASCADE"))
    variety_id: Mapped[int]
    item_id: Mapped[int]
    is_extra: Mapped[bool]
    quantity: Mapped[int] = mapped_column(server_default=text("1"))

    __table_args__ = (
        CheckConstraint("num_nonnulls(booking_id, walk_in_id) = 1", name="for_one_pickup"),
        # The variety really is a kind of that item...
        ForeignKeyConstraint(["variety_id", "item_id"], ["varieties.id", "varieties.item_id"]),
        # ...and is_extra really is what the item says.
        ForeignKeyConstraint(["item_id", "is_extra"], ["items.id", "items.is_extra"]),
        CheckConstraint("quantity >= 1", name="quantity_at_least_1"),
        # E3: one of an extra, never two.
        CheckConstraint("NOT is_extra OR quantity = 1", name="one_of_an_extra"),
        # Each variety once per pickup. More than one of it goes in quantity.
        UniqueConstraint("booking_id", "variety_id"),
        UniqueConstraint("walk_in_id", "variety_id"),
        # E3: one variety of each extra item per pickup, like one bread, even if
        # there are several kinds.
        Index(
            "uq_counter_items_one_extra_per_item_per_booking",
            "booking_id",
            "item_id",
            unique=True,
            postgresql_where=text("is_extra"),
        ),
        Index(
            "uq_counter_items_one_extra_per_item_per_walk_in",
            "walk_in_id",
            "item_id",
            unique=True,
            postgresql_where=text("is_extra"),
        ),
    )
