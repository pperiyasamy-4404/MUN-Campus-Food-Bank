"""The jobs script: everything that happens by itself (S1, B3, I6, P7, P13).

Run it every 15 minutes, from the backend folder:

    .venv/Scripts/python -m app.jobs

On a laptop, Windows Task Scheduler can run it, with run_jobs.cmd. On a real
server, that server's scheduler does.

Each job looks at what's due now, not at when it last ran. So a missed run is
caught up by the next one, and a second run straight after does nothing.

In this order:
1. Make the pickup days for the next two weeks.
2. No-shows: bookings not picked up by the no-show time. Their food goes back on the shelf.
3. Booking details past the retention period: their totals are saved, then they're deleted.
4. The activity log past the retention period.
5. Accounts with no pickup for a year. After 3, so old details don't keep an account.
6. Tidying up: logins, setup codes, wrong tries and holds that ran out.

Each no-show and each day's deletion is a transaction of its own: a short one,
so a student booking or a volunteer counting the shelf never waits long. If a
job fails, the others still run, and the script ends with an error so the
scheduler shows it.

It prints only numbers, never anything about a student (P10).
"""

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db import engine
from app.deps import get_now
from app.models import Settings
from app.services import no_shows, retention
from app.services.pickup_days import make_days_ahead, say_moment

# Only one run at a time: a second one started while the first is still going does nothing.
LOCK_NAME = "campus food bank jobs"


@dataclass
class Report:
    days_made: int = 0
    no_shows: int = 0
    days_deleted: int = 0
    log_rows_deleted: int = 0
    accounts_deleted: int = 0
    tidied: retention.Tidied | None = None
    # Why a job failed, like "no-shows: ...". Never anything about a student.
    problems: list[str] = field(default_factory=list)
    # Another run was still going, so this one did nothing.
    skipped: str | None = None

    def lines(self) -> list[str]:
        if self.skipped:
            return [self.skipped]
        said = []
        if self.days_made:
            said.append(f"Made {_count(self.days_made, 'pickup day')}.")
        if self.no_shows:
            said.append(f"{_count(self.no_shows, 'no-show')}. Their food is back on the shelf.")
        if self.days_deleted:
            said.append(f"Saved the totals and deleted the booking details of {_count(self.days_deleted, 'pickup day')}.")
        if self.log_rows_deleted:
            said.append(f"Deleted {_count(self.log_rows_deleted, 'old activity log line')}.")
        if self.accounts_deleted:
            said.append(f"Deleted {_count(self.accounts_deleted, 'account')} with no pickup for a year.")
        if self.tidied and any(vars(self.tidied).values()):
            t = self.tidied
            said.append(
                f"Tidied up {_count(t.logins, 'login')}, {_count(t.setup_codes, 'setup code')}, "
                f"{_count(t.wrong_tries, 'wrong try', 'wrong tries')} and {_count(t.holds, 'hold')} that ran out."
            )
        said += self.problems
        return said or ["Nothing was due."]


def _count(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else many or one + 's'}"


def run_jobs(engine: Engine, now: datetime) -> Report:
    """Do everything that's due at this moment, each in its own transaction."""
    report = Report()
    with engine.connect() as lock:
        got_it = lock.scalar(text("SELECT pg_try_advisory_lock(hashtextextended(:name, 0))"), {"name": LOCK_NAME})
        lock.commit()
        if not got_it:
            report.skipped = "Another jobs run is still going, so this one did nothing."
            return report
        try:
            _run(engine, now, report)
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(hashtextextended(:name, 0))"), {"name": LOCK_NAME})
            lock.commit()
    return report


def _run(engine: Engine, now: datetime, report: Report) -> None:
    def job[T](name: str, work: Callable[[Session], T]) -> T | None:
        """Do one piece of work in its own transaction. Its answer once it's saved, or None if it failed."""
        with Session(engine) as db:
            try:
                answer = work(db)
                db.commit()
                return answer
            except Exception as problem:  # the other jobs still run
                db.rollback()
                report.problems.append(f"{name} failed: {_say_problem(problem)}")
                return None

    def find[T](look: Callable[[Session], list[T]]) -> list[T]:
        with Session(engine) as db:
            return look(db)

    if find(lambda db: [db.get(Settings, 1)]) == [None]:
        report.problems.append("The food bank settings aren't in the database yet, so nothing was done.")
        return

    # 1.
    made = job("Making pickup days", lambda db: make_days_ahead(db, now))
    report.days_made = len(made or [])

    # 2. One transaction per booking.
    for booking_id in find(lambda db: no_shows.due_no_shows(db, now)):
        if job("No-shows", lambda db: no_shows.mark_no_show(db, booking_id, now)) is not None:
            report.no_shows += 1

    # 3. One transaction per day.
    for day_id in find(lambda db: retention.days_past_retention(db, now)):
        if job("Deleting old booking details", lambda db: retention.save_totals_and_delete(db, day_id)) is not None:
            report.days_deleted += 1

    # 4.
    report.log_rows_deleted = job("Deleting the old activity log", lambda db: retention.delete_old_log(db, now)) or 0

    # 5. One transaction per account.
    for student_id in find(lambda db: retention.quiet_accounts(db, now)):
        if job("Deleting quiet accounts", lambda db: retention.delete_account(db, student_id, now)):
            report.accounts_deleted += 1

    # 6.
    report.tidied = job("Tidying up", lambda db: retention.tidy_up(db, now))


def _say_problem(problem: Exception) -> str:
    """What went wrong, without the database's details: those can show a row's values."""
    if isinstance(problem, DBAPIError) and problem.orig is not None:
        return f"{type(problem.orig).__name__}: {str(problem.orig).splitlines()[0]}"
    return f"{type(problem).__name__}: {problem}"


def main() -> int:
    now = get_now()
    report = run_jobs(engine, now)
    print(f"Jobs, {say_moment(now)}:")
    for line in report.lines():
        print(f"  {line}")
    return 1 if report.problems else 0


if __name__ == "__main__":
    sys.exit(main())
