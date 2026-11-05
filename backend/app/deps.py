"""Things a route asks FastAPI for, instead of making them itself.

A route says `db: DB` and FastAPI hands it a database session. Tests swap these
for their own (a test database, a fixed clock) with app.dependency_overrides,
without changing the route.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db import SessionLocal


def get_db() -> Iterator[Session]:
    """One database session per request, closed when the answer has been sent."""
    with SessionLocal() as db:
        yield db


def get_now() -> datetime:
    """The current moment, in UTC (T1). A function, so a test can stop the clock."""
    return datetime.now(UTC)


DB = Annotated[Session, Depends(get_db)]
Now = Annotated[datetime, Depends(get_now)]
