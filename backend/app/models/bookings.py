from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    SmallInteger,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Hold(Base):
    """A slot kept for a student for 10 minutes while they choose items (S8).

    student_id is the primary key, so a student holds at most one slot.
    A hold past held_until counts as free, so nothing has to delete it on time.
    """

    __tablename__ = "holds"

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), primary_key=True
    )
    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id", ondelete="CASCADE"), index=True)
    held_until: Mapped[datetime]


class Booking(Base):
    """One student's pickup: booked -> packed -> picked up, or cancelled or no-show (B1).

    Which moves between statuses are allowed (B2) is checked in the code, because
    a database rule only sees the new row, not what the status was before.
    """

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    # Stored as well as the slot, so a UNIQUE rule can see the day (S6).
    pickup_day_id: Mapped[int]
    slot_id: Mapped[int] = mapped_column(index=True)
    # What volunteers see and say out loud, instead of anything about the student (P4).
    code: Mapped[str]
    status: Mapped[str] = mapped_column(server_default=text("'booked'"))
    booked_at: Mapped[datetime] = mapped_column(server_default=func.now())
    packed_at: Mapped[datetime | None]
    # Which volunteer pressed Packed (step 6).
    packed_by_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))
    # Who opened the bag to pack it, and when, so the queue can say "Sam is packing"
    # and nobody packs it twice (what-could-go-wrong problem 7, decided 12 Nov).
    # Cleared when it's packed, or when Packed is undone.
    packing_started_at: Mapped[datetime | None]
    packing_by_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))
    picked_up_at: Mapped[datetime | None]
    picked_up_by_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))
    cancelled_at: Mapped[datetime | None]
    cancel_reason: Mapped[str | None]
    no_show_at: Mapped[datetime | None]

    __table_args__ = (
        # The pair (slot, day) must exist in slots, so the day always matches the slot's day.
        ForeignKeyConstraint(["slot_id", "pickup_day_id"], ["slots.id", "slots.pickup_day_id"]),
        CheckConstraint(
            "status IN ('booked', 'packed', 'picked_up', 'cancelled', 'no_show')",
            name="status_is_known",
        ),
        CheckConstraint(
            "cancel_reason IN ('student', 'day_closed', 'walk_in')", name="cancel_reason_is_known"
        ),
        # Among bookings still to come, each student appears once (F2). This also
        # makes a double click on Book harmless: the second booking is refused (B4).
        Index(
            "uq_bookings_one_upcoming_per_student",
            "student_id",
            unique=True,
            postgresql_where=text("status IN ('booked', 'packed')"),
        ),
        # Of any status, so cancelling and booking again can't be used to change items (S6, I7).
        UniqueConstraint("student_id", "pickup_day_id"),
        UniqueConstraint("pickup_day_id", "code"),
        # The status always matches the times saved with it.
        CheckConstraint("status <> 'packed' OR packed_at IS NOT NULL", name="packed_has_a_time"),
        # A packed bag always says who packed it.
        CheckConstraint("(packed_at IS NULL) = (packed_by_staff_id IS NULL)", name="packed_by_a_volunteer"),
        CheckConstraint(
            "(packing_started_at IS NULL) = (packing_by_staff_id IS NULL)", name="packing_has_a_volunteer"
        ),
        CheckConstraint(
            "(status = 'picked_up') = (picked_up_at IS NOT NULL)", name="picked_up_matches_status"
        ),
        # Only a volunteer's click counts as picked up (B3).
        CheckConstraint(
            "(picked_up_at IS NULL) = (picked_up_by_staff_id IS NULL)",
            name="picked_up_by_a_volunteer",
        ),
        CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL)", name="cancelled_matches_status"
        ),
        CheckConstraint(
            "(cancelled_at IS NULL) = (cancel_reason IS NULL)", name="cancel_has_a_reason"
        ),
        CheckConstraint(
            "(status = 'no_show') = (no_show_at IS NOT NULL)", name="no_show_matches_status"
        ),
    )


class BookingItem(Base):
    """One variety a student booked. Its stock was taken when they pressed Book (I5).

    The item limit and "one of each item" are settings, so the code checks them (I3).
    """

    __tablename__ = "booking_items"

    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), primary_key=True
    )
    variety_id: Mapped[int] = mapped_column(ForeignKey("varieties.id"), primary_key=True)
    quantity: Mapped[int] = mapped_column(server_default=text("1"))
    # How many weren't on the shelf when the bag was packed (U4). Their gaps are
    # filled from the substitutes, or by the student at the counter (U6).
    missing: Mapped[int] = mapped_column(server_default=text("0"))

    __table_args__ = (
        CheckConstraint("quantity >= 1", name="quantity_at_least_1"),
        CheckConstraint("missing BETWEEN 0 AND quantity", name="missing_within_quantity"),
    )


class BookingSubstitute(Base):
    """A ranked swap, used only if something the student booked is missing (U2, U4).

    Not taken from stock when booking (U3), only when it goes in the bag. The limit, "not an extra" and "not already in the
    order" need settings or other tables, so the code checks them.
    """

    __tablename__ = "booking_substitutes"

    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), primary_key=True
    )
    rank: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    variety_id: Mapped[int] = mapped_column(ForeignKey("varieties.id"))
    # Empty unless it went in the bag. Then it says which booked food it replaced,
    # for the sticky note: "Sunflower oil -> White rice" (U8).
    replaces_variety_id: Mapped[int | None]

    __table_args__ = (
        CheckConstraint("rank >= 1", name="rank_from_1"),
        UniqueConstraint("booking_id", "variety_id"),
        # It can only replace food booked in the same booking.
        ForeignKeyConstraint(
            ["booking_id", "replaces_variety_id"], ["booking_items.booking_id", "booking_items.variety_id"]
        ),
    )
