"""Deleting what we promised not to keep (P7, P13), and tidying up.

Plain Python with a database session, like the other services. The jobs script
(app/jobs.py) commits.

- Booking details are deleted once the retention period has passed: 90 days
  after the pickup day, with the sample settings. Its totals are saved first,
  in the same transaction (P7). That's the bookings with their food,
  substitutes and counter food, and the walk-ins with theirs.
- The activity log is deleted after the same period (tables.html, choice G).
- An account with no pickup for a year is deleted (P13).
- Things that ran out are deleted: logins, setup codes, wrong tries, holds.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import Date, cast, delete, exists, func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Booking, Hold, LoginFailure, LoginSession, PickupDay, SetupCode, Slot, Student, WalkIn
from app.services import totals
from app.services.pickup_days import NEWFOUNDLAND
from app.services.settings import food_bank_settings

# P13: "Accounts with no pickup for a year are deleted."
A_YEAR = timedelta(days=365)


def _today(now: datetime) -> date:
    return now.astimezone(NEWFOUNDLAND).date()


# ---------- booking details, after the retention period (P7) ----------


def days_past_retention(db: Session, now: datetime) -> list[int]:
    """Pickup days whose details are older than the retention period, and still here.

    With 90 days, Monday 9 November 2026's details are deleted on Monday 8 February 2027.
    """
    settings = food_bank_settings(db)
    last_kept = _today(now) - timedelta(days=settings.retention_days)
    has_details = exists().where(Booking.pickup_day_id == PickupDay.id) | exists().where(
        WalkIn.pickup_day_id == PickupDay.id
    )
    return list(
        db.scalars(
            select(PickupDay.id).where(PickupDay.pickup_date < last_kept, has_details).order_by(PickupDay.pickup_date)
        )
    )


def save_totals_and_delete(db: Session, day_id: int) -> totals.Totals:
    """Add one day's totals to its week, then delete its details, in one transaction.

    The day's row is locked first. If two runs reach the same day, the second
    waits, then finds nothing left to count, so nothing is counted twice.
    The database deletes each booking's food, substitutes and counter food with it
    (ON DELETE CASCADE), and empties the log's link to it.
    """
    day = db.scalar(select(PickupDay).where(PickupDay.id == day_id).with_for_update())
    day_totals = totals.day_totals(db, day)
    totals.add_to_week(db, totals.week_of(day.pickup_date), day_totals)
    db.execute(delete(WalkIn).where(WalkIn.pickup_day_id == day.id))
    db.execute(delete(Booking).where(Booking.pickup_day_id == day.id))
    return day_totals


def delete_old_log(db: Session, now: datetime) -> int:
    """The activity log after the retention period: it says who was served when (choice G)."""
    settings = food_bank_settings(db)
    result = db.execute(delete(AuditLog).where(AuditLog.at < now - timedelta(days=settings.retention_days)))
    return result.rowcount


# ---------- accounts with no pickup for a year (P13) ----------


def _quiet(now: datetime):
    """Accounts whose last pickup, or their start if they never had one, is more than a year ago.

    Kept anyway while they still have a booking or a walk-in on record, like a
    booking for next week, or a setup code that hasn't run out: someone is using it.
    """
    year_ago = _today(now) - A_YEAR
    # The Newfoundland date the account was made.
    started_on = cast(func.timezone("America/St_Johns", Student.created_at), Date)
    return select(Student.id).where(
        func.coalesce(Student.last_pickup_on, started_on) < year_ago,
        ~exists().where(Booking.student_id == Student.id),
        ~exists().where(WalkIn.student_id == Student.id),
        ~exists().where(SetupCode.student_id == Student.id, SetupCode.expires_at > now),
    )


def quiet_accounts(db: Session, now: datetime) -> list[int]:
    return list(db.scalars(_quiet(now).order_by(Student.id)))


def delete_account(db: Session, student_id: int, now: datetime) -> bool:
    """Delete one quiet account, if it's still quiet once it's locked.

    The student's lock comes first, as everywhere: if they're pressing Book at
    this moment, one waits for the other, and a new booking keeps the account.
    Their logins, setup code and hold go with it (ON DELETE CASCADE).
    """
    locked = db.scalar(select(Student.id).where(Student.id == student_id).with_for_update())
    if locked is None or db.scalar(_quiet(now).where(Student.id == student_id)) is None:
        return False
    db.execute(delete(Student).where(Student.id == student_id))
    return True


# ---------- tidying up ----------


@dataclass
class Tidied:
    logins: int
    setup_codes: int
    wrong_tries: int
    holds: int


def tidy_up(db: Session, now: datetime) -> Tidied:
    """Delete what has run out. None of it is used again, and some of it is about students.

    - Logins (sessions) past their end.
    - Setup codes past their end. Trying one gives the same answer as before:
      "doesn't match, or the code has run out".
    - Wrong tries older than the wrong-tries window: only newer ones are counted (P9).
    - Holds on days that are over. A hold that ran out during booking is kept
      until then, so the student is still told their time ran out.
    """
    settings = food_bank_settings(db)
    window = timedelta(minutes=settings.login_window_minutes)
    over = select(Slot.id).join(PickupDay, PickupDay.id == Slot.pickup_day_id).where(PickupDay.no_show_at <= now)
    return Tidied(
        logins=db.execute(delete(LoginSession).where(LoginSession.expires_at <= now)).rowcount,
        setup_codes=db.execute(delete(SetupCode).where(SetupCode.expires_at <= now)).rowcount,
        wrong_tries=db.execute(delete(LoginFailure).where(LoginFailure.failed_at <= now - window)).rowcount,
        holds=db.execute(delete(Hold).where(Hold.slot_id.in_(over))).rowcount,
    )
