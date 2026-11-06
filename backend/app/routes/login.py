"""Logging in and out, and setting a password with a setup code (P6, R1, R3).

ID numbers and passwords only ever come in the body of a POST, never in the
web address, so they can't end up in a browser's history or a server log (P10).
"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from app.deps import DB, DeviceCookie, Login, LoginTicket, Now
from app.models import Staff, Student
from app.security.inputs import IdNumber, NewPassword, Password, SetupCode, Username
from app.security.keyed_hash import id_hash, username_hash
from app.security.sessions import clear_login_cookie, end_session, set_login_cookie, start_session
from app.security.wrong_tries import set_device_cookie
from app.services import accounts
from app.services.pickup_days import NEWFOUNDLAND

router = APIRouter(prefix="/api")


# ---------- what comes in ----------


class StudentLogin(BaseModel):
    id_number: IdNumber
    password: Password


class StudentSetup(BaseModel):
    id_number: IdNumber
    setup_code: SetupCode
    new_password: NewPassword


class StaffLogin(BaseModel):
    username: Username
    password: Password


class StaffSetup(BaseModel):
    username: Username
    setup_code: SetupCode
    new_password: NewPassword


# ---------- what goes out ----------


class StudentMe(BaseModel):
    """Nothing about the student but what they need to see (P3)."""

    kind: Literal["student"] = "student"
    # Shown as "Your password was reset on 4 Nov" (R4).
    password_reset_at: datetime | None


class StaffMe(BaseModel):
    kind: Literal["staff"] = "staff"
    username: str
    role: Literal["volunteer", "coordinator"]


Me = Annotated[StudentMe | StaffMe, Field(discriminator="kind")]


def about(account: Student | Staff) -> StudentMe | StaffMe:
    if isinstance(account, Student):
        reset_at = account.password_reset_at
        return StudentMe(password_reset_at=reset_at.astimezone(NEWFOUNDLAND) if reset_at else None)
    return StaffMe(username=account.username, role=account.role)  # type: ignore[arg-type]


def logged_in(db: DB, response: Response, account: Student | Staff, who_hash: str, now: datetime) -> StudentMe | StaffMe:
    """Start the login, save everything, and hand the browser its cookies."""
    ticket, lifetime = start_session(db, account, now)
    db.commit()
    set_login_cookie(response, ticket, lifetime)
    # This browser has now logged in to this account, so its wrong tries count on their own (P9).
    set_device_cookie(response, who_hash)
    return about(account)


# ---------- the addresses ----------


@router.post("/student/login")
def student_login(details: StudentLogin, db: DB, now: Now, response: Response, device: DeviceCookie = None) -> StudentMe:
    id_number = details.id_number.get_secret_value()
    student = accounts.log_in_student(db, id_number, details.password.get_secret_value(), device, now)
    return logged_in(db, response, student, id_hash(id_number), now)  # type: ignore[return-value]


@router.post("/student/setup")
def student_setup(details: StudentSetup, db: DB, now: Now, response: Response, device: DeviceCookie = None) -> StudentMe:
    """Use a setup code from the counter to choose a password, then stay logged in."""
    id_number = details.id_number.get_secret_value()
    student = accounts.set_student_password(
        db,
        id_number,
        details.setup_code.get_secret_value(),
        details.new_password.get_secret_value(),
        device,
        now,
    )
    return logged_in(db, response, student, id_hash(id_number), now)  # type: ignore[return-value]


@router.post("/staff/login")
def staff_login(details: StaffLogin, db: DB, now: Now, response: Response, device: DeviceCookie = None) -> StaffMe:
    staff = accounts.log_in_staff(db, details.username, details.password.get_secret_value(), device, now)
    return logged_in(db, response, staff, username_hash(details.username), now)  # type: ignore[return-value]


@router.post("/staff/setup")
def staff_setup(details: StaffSetup, db: DB, now: Now, response: Response, device: DeviceCookie = None) -> StaffMe:
    staff = accounts.set_staff_password(
        db,
        details.username,
        details.setup_code.get_secret_value(),
        details.new_password.get_secret_value(),
        device,
        now,
    )
    return logged_in(db, response, staff, username_hash(details.username), now)  # type: ignore[return-value]


@router.post("/logout", status_code=204)
def log_out(db: DB, response: Response, ticket: LoginTicket = None) -> None:
    """Ends this login only. The trusted-device cookie stays: it isn't a login."""
    if ticket is not None:
        end_session(db, ticket)
        db.commit()
    clear_login_cookie(response)


@router.get("/me")
def who_am_i(login: Login, db: DB) -> Me | None:
    """Who is logged in on this browser, or null if nobody is."""
    if login is None:
        return None
    account = db.get(Student, login.student_id) if login.student_id else db.get(Staff, login.staff_id)
    if account is None or (isinstance(account, Staff) and account.disabled_at is not None):
        return None
    return about(account)
