"""Accounts and logging in: setup codes, passwords, and who did what (P1-P10, R1-R4).

Everything here is plain Python with a database session: no cookies, no web
addresses. app/routes/login.py and app/routes/accounts.py turn it into web
addresses, and tests can check each rule straight from here.

The routes commit. The one exception is a wrong try, which is saved the moment
it happens (see count_wrong_try).
"""

import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Settings, SetupCode, Staff, Student
from app.security.keyed_hash import id_hash, username_hash
from app.security.passwords import hash_password, needs_new_hash, password_matches
from app.security.sessions import end_every_session, end_old_sessions
from app.security.setup_codes import new_setup_code, setup_code_hash
from app.security.wrong_tries import (
    count_wrong_try,
    forget_wrong_tries,
    tries_counted_under,
    wait_until,
)

Account = Student | Staff


# ---------- what can go wrong ----------


class AccountProblem(Exception):
    """Something the person can fix. The message is shown to them as it is."""

    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class WrongDetails(AccountProblem):
    """The same words whatever was wrong: no account, no password set yet, the
    wrong password, a wrong or expired code. So the answer never tells anyone
    whether a number has an account (P9)."""

    status_code = 401


class TooManyTries(AccountProblem):
    status_code = 429

    def __init__(self, next_try_at: datetime, now: datetime):
        self.retry_after_seconds = max(1, ceil((next_try_at - now).total_seconds()))
        minutes = ceil(self.retry_after_seconds / 60)
        super().__init__(f"Too many wrong tries. Try again in {minutes} minute{'' if minutes == 1 else 's'}.")


class NameTaken(AccountProblem):
    status_code = 409


class NotFound(AccountProblem):
    status_code = 404


WRONG_STUDENT_PASSWORD = "That ID number and password don't match."
WRONG_STUDENT_CODE = "That ID number and setup code don't match, or the code has run out."
WRONG_STAFF_PASSWORD = "That username and password don't match."
WRONG_STAFF_CODE = "That username and setup code don't match, or the code has run out."


@dataclass
class IssuedCode:
    """A setup code to show once, at the counter or from the setup script. Never saved."""

    code: str
    expires_at: datetime
    new_account: bool = False


# ---------- at the counter (R1) ----------


def give_student_setup_code(db: Session, id_number: str, volunteer: Staff, now: datetime) -> IssuedCode:
    """The volunteer has checked the student's MUN card and typed its number.

    A new card gets an account. A card that already has one gets a new code,
    which is how a forgotten password is reset. The old password keeps working
    until the new code is used, so a code given by mistake locks nobody out.
    """
    student = db.scalar(select(Student).where(Student.id_hash == id_hash(id_number)))
    new_account = student is None
    if student is None:
        student = Student(id_hash=id_hash(id_number), created_at=now, created_by_staff_id=volunteer.id)
        db.add(student)
        db.flush()
        log(db, volunteer, "created_student", now, student=student)
    issued = _give_setup_code(db, student, volunteer, now)
    issued.new_account = new_account
    return issued


# ---------- students, on their own phone ----------


def set_student_password(
    db: Session, id_number: str, code: str, new_password: str, device_cookie: str | None, now: datetime
) -> Student:
    """ID number and setup code, then a password only the student knows (R1).

    Logs the student out everywhere else. If they had a password before, it
    counts as a reset, and they'll see "password reset on DATE" (R4).
    """
    if new_password == id_number:
        raise AccountProblem("Choose a password that isn't your ID number.")
    student = db.scalar(select(Student).where(Student.id_hash == id_hash(id_number)))
    _use_setup_code(db, student, code, id_hash(id_number), device_cookie, now, WRONG_STUDENT_CODE)
    assert student is not None  # _use_setup_code refuses when there's no account
    if student.password_hash is not None:
        student.password_reset_at = now
    student.password_hash = hash_password(new_password)
    return student


def log_in_student(db: Session, id_number: str, password: str, device_cookie: str | None, now: datetime) -> Student:
    """P6: the ID number and the password, checked against the HMAC and the argon2 hash."""
    student = db.scalar(select(Student).where(Student.id_hash == id_hash(id_number)))
    _check_password(db, student, password, id_hash(id_number), device_cookie, now, WRONG_STUDENT_PASSWORD)
    assert student is not None  # _check_password refuses when there's no account
    return student


# ---------- staff ----------


def set_staff_password(
    db: Session, username: str, code: str, new_password: str, device_cookie: str | None, now: datetime
) -> Staff:
    """The same as for students: the coordinator never sees the password (R3)."""
    if new_password.lower() == username.lower():
        raise AccountProblem("Choose a password that isn't your username.")
    staff = _active_staff_named(db, username)
    _use_setup_code(db, staff, code, username_hash(username), device_cookie, now, WRONG_STAFF_CODE)
    assert staff is not None
    staff.password_hash = hash_password(new_password)
    return staff


def log_in_staff(db: Session, username: str, password: str, device_cookie: str | None, now: datetime) -> Staff:
    """A switched-off account logs in to nothing, with the same words as a wrong password."""
    staff = _active_staff_named(db, username)
    _check_password(db, staff, password, username_hash(username), device_cookie, now, WRONG_STAFF_PASSWORD)
    assert staff is not None
    return staff


# ---------- the coordinator (R3) ----------


def add_volunteer(db: Session, username: str, coordinator: Staff, now: datetime) -> tuple[Staff, IssuedCode]:
    """A new volunteer account, with a setup code to give them."""
    if _staff_named(db, username) is not None:
        raise NameTaken(f"There's already an account called {username}. Try adding an initial, like {username} B.")
    volunteer = Staff(username=username, role="volunteer", created_at=now, created_by_staff_id=coordinator.id)
    db.add(volunteer)
    db.flush()
    log(db, coordinator, "created_volunteer", now, staff=volunteer)
    issued = _give_setup_code(db, volunteer, coordinator, now)
    issued.new_account = True
    return volunteer, issued


def give_volunteer_setup_code(db: Session, volunteer: Staff, coordinator: Staff, now: datetime) -> IssuedCode:
    """For a volunteer who hasn't set a password yet, lost their code, or forgot their password."""
    if volunteer.disabled_at is not None:
        raise AccountProblem(f"{volunteer.username}'s account is switched off.")
    return _give_setup_code(db, volunteer, coordinator, now)


def switch_off_volunteer(db: Session, volunteer: Staff, coordinator: Staff, now: datetime) -> None:
    """A volunteer who leaves can't log in again, starting now.

    The account itself is kept, so the log can still say who did what (R4).
    """
    if volunteer.disabled_at is not None:
        return
    volunteer.disabled_at = now
    db.execute(delete(SetupCode).where(SetupCode.staff_id == volunteer.id))
    end_every_session(db, volunteer)
    log(db, coordinator, "switched_off_volunteer", now, staff=volunteer)


def volunteer_with_id(db: Session, staff_id: int) -> Staff:
    """Only volunteers: the coordinator's own account is looked after by the setup script."""
    volunteer = db.get(Staff, staff_id)
    if volunteer is None or volunteer.role != "volunteer":
        raise NotFound("There's no volunteer with that number.")
    return volunteer


def set_up_first_coordinator(db: Session, username: str, now: datetime) -> IssuedCode:
    """Run once on the server when the system is installed (R3). There is no web page for it.

    Run again with the same username, it gives that coordinator a new code,
    for a forgotten password. It never makes a second coordinator.
    """
    named = _staff_named(db, username)
    if named is not None:
        if named.role != "coordinator":
            raise AccountProblem(f"{named.username} is a volunteer, not the coordinator.")
        return _give_setup_code(db, named, None, now)

    coordinators = db.scalars(select(Staff.username).where(Staff.role == "coordinator")).all()
    if coordinators:
        raise AccountProblem(
            f"The coordinator is already set up: {', '.join(coordinators)}. "
            "To give them a new setup code, run this again with that username."
        )
    coordinator = Staff(username=username, role="coordinator", created_at=now, created_by_staff_id=None)
    db.add(coordinator)
    db.flush()
    log(db, None, "created_coordinator", now, staff=coordinator)
    issued = _give_setup_code(db, coordinator, None, now)
    issued.new_account = True
    return issued


# ---------- shared steps ----------


def food_bank_settings(db: Session) -> Settings:
    settings = db.get(Settings, 1)
    if settings is None:
        raise LookupError("The settings row is missing")
    return settings


def log(
    db: Session,
    by: Staff | None,
    action: str,
    now: datetime,
    *,
    student: Student | None = None,
    staff: Staff | None = None,
) -> None:
    """One line in the audit log (R4). by=None means the setup script."""
    db.add(
        AuditLog(
            at=now,
            staff_id=by.id if by else None,
            action=action,
            student_id=student.id if student else None,
            affected_staff_id=staff.id if staff else None,
        )
    )


def _give_setup_code(db: Session, account: Account, by: Staff | None, now: datetime) -> IssuedCode:
    """A new code for the account, replacing any earlier one, so each account has at most one."""
    is_student = isinstance(account, Student)
    db.execute(delete(SetupCode).where(_setup_code_of(account)))
    code = new_setup_code()
    expires_at = now + timedelta(days=food_bank_settings(db).setup_code_days)
    db.add(
        SetupCode(
            code_hash=setup_code_hash(code),
            student_id=account.id if is_student else None,
            staff_id=None if is_student else account.id,
            issued_by_staff_id=by.id if by else None,
            issued_at=now,
            expires_at=expires_at,
        )
    )
    if is_student:
        log(db, by, "issued_setup_code", now, student=account)
    else:
        log(db, by, "issued_setup_code", now, staff=account)
    return IssuedCode(code=code, expires_at=expires_at)


def _use_setup_code(
    db: Session,
    account: Account | None,
    typed_code: str,
    who_hash: str,
    device_cookie: str | None,
    now: datetime,
    wrong: str,
) -> None:
    """Check the code, then use it up. Wrong codes count as wrong tries, like passwords."""
    counted_under = tries_counted_under(who_hash, device_cookie)
    next_try_at = wait_until(db, counted_under, food_bank_settings(db), now)
    if next_try_at is not None:
        raise TooManyTries(next_try_at, now)

    setup_code = None if account is None else db.scalar(select(SetupCode).where(_setup_code_of(account)))
    if (
        setup_code is None
        or setup_code.expires_at <= now
        # compare_digest takes as long whether the first or the last character is wrong.
        or not hmac.compare_digest(setup_code.code_hash, setup_code_hash(typed_code))
    ):
        count_wrong_try(db, counted_under, now)
        raise WrongDetails(wrong)

    db.delete(setup_code)  # it works once (R1)
    end_every_session(db, account)  # a new password logs out every old login
    forget_wrong_tries(db, counted_under)


def _check_password(
    db: Session,
    account: Account | None,
    password: str,
    who_hash: str,
    device_cookie: str | None,
    now: datetime,
    wrong: str,
) -> None:
    counted_under = tries_counted_under(who_hash, device_cookie)
    next_try_at = wait_until(db, counted_under, food_bank_settings(db), now)
    if next_try_at is not None:
        raise TooManyTries(next_try_at, now)

    # With no account, this still checks against a made-up hash, so it takes as long.
    if not password_matches(account.password_hash if account else None, password):
        count_wrong_try(db, counted_under, now)
        raise WrongDetails(wrong)

    assert account is not None and account.password_hash is not None
    if needs_new_hash(account.password_hash):
        account.password_hash = hash_password(password)
    forget_wrong_tries(db, counted_under)
    end_old_sessions(db, account, now)


def _staff_named(db: Session, username: str) -> Staff | None:
    """Capitals don't matter: "Sam" and "sam" are the same account (uq_staff_username_lower)."""
    return db.scalar(select(Staff).where(func.lower(Staff.username) == username.lower()))


def _active_staff_named(db: Session, username: str) -> Staff | None:
    staff = _staff_named(db, username)
    return staff if staff is not None and staff.disabled_at is None else None


def _setup_code_of(account: Account):
    if isinstance(account, Student):
        return SetupCode.student_id == account.id
    return SetupCode.staff_id == account.id
