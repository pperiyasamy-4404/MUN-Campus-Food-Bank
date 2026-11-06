"""Things a route asks FastAPI for, instead of making them itself.

A route says `db: DB` and FastAPI hands it a database session. Tests swap these
for their own (a test database, a fixed clock) with app.dependency_overrides,
without changing the route.

The login ones work the same way. A route that says `student: CurrentStudent`
only runs for a logged-in student. Anyone else gets "Please log in." before the
route's own code starts, so no route can forget the check.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import LoginSession, Staff, Student
from app.security.sessions import COOKIE, STUDENT_LOGIN, find_session, keep_student_logged_in, set_login_cookie
from app.security.wrong_tries import DEVICE_COOKIE


def get_db() -> Iterator[Session]:
    """One database session per request, closed when the answer has been sent."""
    with SessionLocal() as db:
        yield db


def get_now() -> datetime:
    """The current moment, in UTC (T1). A function, so a test can stop the clock."""
    return datetime.now(UTC)


DB = Annotated[Session, Depends(get_db)]
Now = Annotated[datetime, Depends(get_now)]
# The login ticket and the trusted-device cookie, if the browser sent them.
LoginTicket = Annotated[str | None, Cookie(alias=COOKIE)]
DeviceCookie = Annotated[str | None, Cookie(alias=DEVICE_COOKIE)]


def get_login(db: DB, now: Now, response: Response, ticket: LoginTicket = None) -> LoginSession | None:
    """Who sent this request, from the ticket in their cookie. None if nobody is logged in.

    A student's login moves on to 30 days from now, at most once a day, and the
    cookie moves with it.
    """
    if ticket is None:
        return None
    login = find_session(db, ticket, now)
    if login is not None and keep_student_logged_in(login, now):
        db.commit()
        set_login_cookie(response, ticket, STUDENT_LOGIN)
    return login


Login = Annotated[LoginSession | None, Depends(get_login)]


def get_student(login: Login, db: DB) -> Student:
    if login is None or login.student_id is None:
        raise HTTPException(401, "Please log in.")
    student = db.get(Student, login.student_id)
    assert student is not None  # deleting a student deletes their sessions
    return student


def get_staff(login: Login, db: DB) -> Staff:
    """A volunteer or the coordinator."""
    staff = None if login is None or login.staff_id is None else db.get(Staff, login.staff_id)
    # Switching an account off deletes its sessions. This is a second check.
    if staff is None or staff.disabled_at is not None:
        raise HTTPException(401, "Please log in.")
    return staff


CurrentStudent = Annotated[Student, Depends(get_student)]
CurrentStaff = Annotated[Staff, Depends(get_staff)]


def get_coordinator(staff: CurrentStaff) -> Staff:
    if staff.role != "coordinator":
        raise HTTPException(403, "Only the coordinator can do this.")
    return staff


CurrentCoordinator = Annotated[Staff, Depends(get_coordinator)]
