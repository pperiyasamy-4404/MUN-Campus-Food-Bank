"""The real server, for the load test: the test database, plain http, and a moved clock.

Started by loadtest/run.py, like this:

    python -m uvicorn loadtest.serve:app --port 8077 --workers 1

LOADTEST_SHIFT_SECONDS moves the clock, so the server thinks it's, say, Sunday
at 4:59 pm when booking is about to open. Every worker reads the same number,
so they all agree on the time. Nothing else about the app is changed: the same
routes, the same database pool, the same locks as in real use.
"""

import os
from datetime import UTC, datetime, timedelta

from app.config import config

# Before app.db is imported, so every session uses the test database (like app.demo).
config.database_url = config.test_database_url
config.cookie_secure = False

from app.deps import get_now  # noqa: E402
from app.main import app  # noqa: E402

SHIFT = timedelta(seconds=float(os.environ.get("LOADTEST_SHIFT_SECONDS", "0")))


def moved_clock() -> datetime:
    return datetime.now(UTC) + SHIFT


app.dependency_overrides[get_now] = moved_clock
