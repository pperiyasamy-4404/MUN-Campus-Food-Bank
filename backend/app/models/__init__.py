"""Every table. Importing this package registers them all with Base.metadata, which Alembic reads.

The design, and the reason for each rule, is in tables.html at the top of the repository.
"""

from app.models.bookings import Booking, BookingItem, BookingSubstitute, Hold
from app.models.days import PickupDay, PickupHours, Settings, Slot
from app.models.food import Category, Item, Tag, Variety, VarietyTag
from app.models.people import AuditLog, LoginFailure, LoginSession, SetupCode, Staff, Student

__all__ = [
    "AuditLog",
    "Booking",
    "BookingItem",
    "BookingSubstitute",
    "Category",
    "Hold",
    "Item",
    "LoginFailure",
    "LoginSession",
    "PickupDay",
    "PickupHours",
    "Settings",
    "SetupCode",
    "Slot",
    "Staff",
    "Student",
    "Tag",
    "Variety",
    "VarietyTag",
]
