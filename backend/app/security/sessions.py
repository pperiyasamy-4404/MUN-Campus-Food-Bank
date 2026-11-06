"""Logins: a random ticket in a cookie, and a hash of it in the sessions table.

How long a login lasts (decided 5 Nov 2026):
- students: 30 days after their last visit, so booking night needs no password
- staff: 12 hours after logging in, so the counter laptop never stays logged in overnight
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import config
from app.models import LoginSession, Staff, Student

COOKIE = "session"
STUDENT_LOGIN = timedelta(days=30)
STAFF_LOGIN = timedelta(hours=12)


def ticket_hash(ticket: str) -> str:
    """A plain SHA-256 is enough here, unlike for ID numbers.

    A ticket is 256 random bits, so nobody can list every possible ticket the
    way they could list every 9-digit number. If the database leaked, the
    hashes couldn't be turned back into tickets that log anyone in.
    """
    return hashlib.sha256(ticket.encode()).hexdigest()


def start_session(db: Session, account: Student | Staff, now: datetime) -> tuple[str, timedelta]:
    """Log the account in. Returns the ticket for the cookie, and how long it lasts."""
    is_student = isinstance(account, Student)
    lifetime = STUDENT_LOGIN if is_student else STAFF_LOGIN
    ticket = secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            token_hash=ticket_hash(ticket),
            student_id=account.id if is_student else None,
            staff_id=None if is_student else account.id,
            created_at=now,
            expires_at=now + lifetime,
        )
    )
    return ticket, lifetime


def find_session(db: Session, ticket: str, now: datetime) -> LoginSession | None:
    """The login this ticket belongs to, if it hasn't run out."""
    login = db.get(LoginSession, ticket_hash(ticket))
    if login is None or login.expires_at <= now:
        return None
    return login


def keep_student_logged_in(login: LoginSession, now: datetime) -> bool:
    """Move a student's login on to 30 days from now. Staff logins never move.

    Done at most once a day, so not every visit writes to the database.
    Returns True if it moved, so the cookie can be moved too.
    """
    if login.student_id is None or login.expires_at - now > STUDENT_LOGIN - timedelta(days=1):
        return False
    login.expires_at = now + STUDENT_LOGIN
    return True


def end_session(db: Session, ticket: str) -> None:
    db.execute(delete(LoginSession).where(LoginSession.token_hash == ticket_hash(ticket)))


def end_every_session(db: Session, account: Student | Staff) -> None:
    """Log the account out everywhere at once, for example after a password reset.

    This is the reason we chose sessions over tokens (JWT): one delete, and a
    flatmate who was logged in on the student's laptop is out straight away.
    """
    db.execute(delete(LoginSession).where(_belongs_to(account)))


def end_old_sessions(db: Session, account: Student | Staff, now: datetime) -> None:
    """Tidy up logins of this account that have run out."""
    db.execute(delete(LoginSession).where(_belongs_to(account), LoginSession.expires_at <= now))


def sessions_of(db: Session, account: Student | Staff) -> list[LoginSession]:
    return list(db.scalars(select(LoginSession).where(_belongs_to(account))))


def _belongs_to(account: Student | Staff):
    if isinstance(account, Student):
        return LoginSession.student_id == account.id
    return LoginSession.staff_id == account.id


def set_login_cookie(response: Response, ticket: str, lifetime: timedelta) -> None:
    """HttpOnly: code on the page can't read it. SameSite=Strict: another website
    can't make the browser send it. Secure: only over https."""
    response.set_cookie(
        COOKIE,
        ticket,
        max_age=int(lifetime.total_seconds()),
        httponly=True,
        secure=config.cookie_secure,
        samesite="strict",
    )


def clear_login_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE, httponly=True, secure=config.cookie_secure, samesite="strict")
