"""Slowing down password guessing, without letting anyone lock a student out (P9).

Every wrong password or setup code adds a row to login_failures. Before checking
a password, we count that account's rows from the last 15 minutes. After 5, the
answer is "wait", and the password isn't even checked, so guessing gets no faster.
Once the oldest of those tries is 15 minutes old, one more try is allowed.
That's 5 tries per 15 minutes, never a lock that someone has to undo.

The catch: anyone who knows a student's ID number could type 5 wrong passwords
every 15 minutes and keep the real student waiting on booking night. So a
browser that has logged in to the account before gets a "trusted device"
cookie, and its tries are counted on their own. Someone else's wrong tries
don't slow down the student's own phone. (This is OWASP's "device cookie" idea.)
"""

import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import Response
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.config import config
from app.models import LoginFailure, Settings
from app.security.keyed_hash import keyed_hash

DEVICE_COOKIE = "device"
DEVICE_COOKIE_LIFETIME = timedelta(days=365)


def device_cookie_for(who_hash: str) -> str:
    """A cookie that says "this browser has logged in to this account before".

    A random part and a signature. Only the server has the key, so nobody can
    make one for someone else's account.
    """
    token = secrets.token_urlsafe(16)
    return f"{token}.{_signature(who_hash, token)}"


def tries_counted_under(who_hash: str, device_cookie: str | None) -> str:
    """Whose wrong tries to count: this trusted device's own, or the account's shared ones.

    who_hash is the keyed hash of the number or username that was typed, whether
    or not it has an account, so made-up numbers are slowed down too.
    """
    if device_cookie:
        token, _, signature = device_cookie.partition(".")
        expected = _signature(who_hash, token)
        if token and hmac.compare_digest(signature.encode(), expected.encode()):
            return keyed_hash("trusted-device-tries", token)
    return who_hash


def wait_until(db: Session, counted_under: str, settings: Settings, now: datetime) -> datetime | None:
    """None if a try is allowed now. Otherwise, the moment the next one is.

    First it takes a lock on this name, held until the answer is saved. Without
    it, 50 tries sent at the same moment would all count 0 earlier wrong tries
    and all be checked.
    """
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:name, 0))"), {"name": counted_under})
    window = timedelta(minutes=settings.login_window_minutes)
    recent = db.scalars(
        select(LoginFailure.failed_at)
        .where(LoginFailure.who_hash == counted_under, LoginFailure.failed_at > now - window)
        .order_by(LoginFailure.failed_at.desc())
        .limit(settings.login_tries)
    ).all()
    if len(recent) < settings.login_tries:
        return None
    # The oldest of the last 5 tries leaves the 15 minutes first, and frees up one try.
    return recent[-1] + window


def count_wrong_try(db: Session, counted_under: str, now: datetime) -> None:
    """Save one wrong try, straight away.

    It's committed here, because the error answer that follows would otherwise
    undo it, and the guesser would never be slowed down.
    """
    db.add(LoginFailure(who_hash=counted_under, failed_at=now))
    db.commit()


def forget_wrong_tries(db: Session, counted_under: str) -> None:
    """After a right password, earlier slips don't count any more."""
    db.execute(delete(LoginFailure).where(LoginFailure.who_hash == counted_under))


def set_device_cookie(response: Response, who_hash: str) -> None:
    response.set_cookie(
        DEVICE_COOKIE,
        device_cookie_for(who_hash),
        max_age=int(DEVICE_COOKIE_LIFETIME.total_seconds()),
        httponly=True,
        secure=config.cookie_secure,
        samesite="strict",
    )


def _signature(who_hash: str, token: str) -> str:
    return keyed_hash("trusted-device", f"{who_hash}:{token}")
