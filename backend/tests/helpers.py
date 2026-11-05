"""Helpers for tests that use the database: making rows, and expecting a rule to refuse."""

import secrets
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.deps import get_now
from app.main import app
from app.models import Booking, Category, Item, PickupDay, Settings, Slot, Staff, Student, Variety
from app.sample_data import SAMPLE_SETTINGS

MONDAY = date(2026, 11, 9)


@contextmanager
def refused_by(db, rule: str):
    """Expect the database to refuse what happens inside the block, because of the named rule.

    Checking the rule's name makes sure the test fails for the right reason, not
    because some other rule (like a missing value) happened to refuse it.
    """
    with pytest.raises(IntegrityError) as refusal:
        with db.begin_nested():
            yield
            db.flush()
    refused_rule = refusal.value.orig.diag.constraint_name
    assert refused_rule == rule, f"refused by {refused_rule}, not {rule}"


def stop_the_clock_at(moment: datetime) -> None:
    """Make the server think it is this moment. The client fixture puts the real clock back."""
    app.dependency_overrides[get_now] = lambda: moment


def new_hash() -> str:
    """A made-up HMAC: 64 characters of 0-9 and a-f."""
    return secrets.token_hex(32)


def add(db, row):
    db.add(row)
    db.flush()
    return row


def make_settings(db, **changes) -> Settings:
    return add(db, Settings(**(SAMPLE_SETTINGS | changes)))


def make_staff(db, username: str | None = None, role: str = "volunteer") -> Staff:
    return add(db, Staff(username=username or f"volunteer-{secrets.token_hex(3)}", role=role))


def make_student(db) -> Student:
    return add(db, Student(id_hash=new_hash(), created_by_staff_id=make_staff(db).id))


def make_day(db, on: date = MONDAY) -> PickupDay:
    """A pickup day with sample times: opens 5 pm the day before, closes 12 pm, no-show 6 pm."""
    opens = datetime.combine(on - timedelta(days=1), time(20, 30), tzinfo=UTC)
    return add(
        db,
        PickupDay(
            pickup_date=on,
            booking_opens_at=opens,
            booking_closes_at=opens + timedelta(hours=19),
            no_show_at=opens + timedelta(hours=25),
        ),
    )


def make_slot(db, day: PickupDay | None = None, capacity: int = 1, minutes_in: int = 0) -> Slot:
    day = day or make_day(db)
    starts_at = datetime.combine(day.pickup_date, time(19, 0), tzinfo=UTC) + timedelta(minutes=minutes_in)
    return add(db, Slot(pickup_day_id=day.id, starts_at=starts_at, capacity=capacity))


def make_variety(db, stock: int = 5) -> Variety:
    name = secrets.token_hex(3)
    category = add(db, Category(name=f"Category {name}"))
    item = add(db, Item(name=f"Item {name}", category_id=category.id))
    return add(db, Variety(item_id=item.id, name=f"Variety {name}", stock=stock))


def make_booking(db, student: Student | None = None, slot: Slot | None = None, code: str = "K3P", **columns) -> Booking:
    student = student or make_student(db)
    slot = slot or make_slot(db)
    return add(
        db,
        Booking(student_id=student.id, slot_id=slot.id, pickup_day_id=slot.pickup_day_id, code=code, **columns),
    )
