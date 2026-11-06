from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Identity, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Staff(Base):
    """Volunteers and the coordinator (R2, R3).

    Never deleted, only disabled, so the log can still say who did what.
    """

    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    username: Mapped[str]
    role: Mapped[str]
    # Empty until they set a password with their setup code.
    password_hash: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # Empty only for the first coordinator, made by the setup script.
    created_by_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))
    disabled_at: Mapped[datetime | None]

    __table_args__ = (
        CheckConstraint("role IN ('volunteer', 'coordinator')", name="role_is_known"),
        # Only an argon2 hash fits, so a password typed in can never be saved as text (P8).
        CheckConstraint("password_hash LIKE '$argon2id$%'", name="password_hash_is_argon2"),
        # "Sam" and "sam" would be the same person, so every log line names one volunteer (R4).
        Index("uq_staff_username_lower", text("lower(username)"), unique=True),
    )


class Student(Base):
    """One row per MUN card. No name, contact details or ID number, ever (P2, P3)."""

    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    # The HMAC of the ID number. One card, one account (P1).
    id_hash: Mapped[str] = mapped_column(unique=True)
    # Empty until they set a password with their setup code.
    password_hash: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    created_by_staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"))
    # Shown to the student as "password reset on DATE" (R4).
    password_reset_at: Mapped[datetime | None]
    # The Newfoundland date of the last pickup. Booking details are deleted after
    # the retention period, but the year rule still needs this date (F1, P13).
    last_pickup_on: Mapped[date | None]

    __table_args__ = (
        # An HMAC is 64 characters of 0-9 and a-f, so a raw 9-digit ID number
        # can never be saved here by mistake (P2).
        CheckConstraint("id_hash ~ '^[0-9a-f]{64}$'", name="id_hash_looks_like_hmac"),
        # Only an argon2 hash fits, so a password typed in can never be saved as text (P8).
        CheckConstraint("password_hash LIKE '$argon2id$%'", name="password_hash_is_argon2"),
    )


class LoginSession(Base):
    """Who is logged in. Holds a hash of the ticket in the cookie, never the ticket itself.

    A password reset deletes the account's rows here, which logs it out at once.
    """

    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(primary_key=True)
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    staff_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]

    __table_args__ = (
        CheckConstraint("num_nonnulls(student_id, staff_id) = 1", name="belongs_to_one_account"),
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="token_hash_looks_like_hash"),
    )


class SetupCode(Base):
    """One-time codes given at the counter (R1, R3).

    Deleted the moment they're used, and replaced when a new one is issued,
    so each account has at most one. The audit log keeps who issued it.
    """

    __tablename__ = "setup_codes"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    code_hash: Mapped[str]
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), unique=True
    )
    staff_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff.id", ondelete="CASCADE"), unique=True
    )
    # Empty only for the first coordinator's codes, made by the setup script (R3).
    issued_by_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))
    issued_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]

    __table_args__ = (
        CheckConstraint("num_nonnulls(student_id, staff_id) = 1", name="belongs_to_one_account"),
        CheckConstraint("expires_at > issued_at", name="expires_after_issued"),
        # An HMAC, so the code itself is never saved: someone reading the
        # database can't use a code before the student does.
        CheckConstraint("code_hash ~ '^[0-9a-f]{64}$'", name="code_hash_looks_like_hmac"),
    )


class LoginFailure(Base):
    """One row per wrong password, counted to slow down guessing (P9).

    No link to students on purpose: tries against a number with no account are
    slowed down too, so the speed of the answer never tells anyone which numbers
    have accounts.
    """

    __tablename__ = "login_failures"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    # The HMAC of whatever number (or username) was typed.
    who_hash: Mapped[str]
    failed_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        CheckConstraint("who_hash ~ '^[0-9a-f]{64}$'", name="who_hash_looks_like_hmac"),
        Index("ix_login_failures_who_hash_failed_at", "who_hash", "failed_at"),
    )


class AuditLog(Base):
    """Who did what: accounts, setup codes, walk-ins, pickups and fixes (R4, B6).

    Deleted after the retention period, like booking details (P7).
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    at: Mapped[datetime] = mapped_column(server_default=func.now())
    # Who did it. Empty only when the setup script did it, on the server itself
    # (the first coordinator, R3).
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))
    # For example "created_student" or "fixed_no_show_to_picked_up".
    action: Mapped[str]
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id", ondelete="SET NULL")
    )
    # The staff account it was done to, like the volunteer who was given a setup code.
    affected_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))
    booking_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookings.id", ondelete="SET NULL")
    )
