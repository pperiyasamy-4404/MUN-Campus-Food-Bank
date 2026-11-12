"""Three accounts for trying the app on this computer, in the WORKING database.

Run from backend/:

    .venv\\Scripts\\python -m app.dev_accounts

It makes (or puts back) these, all with the password "Password":
- Admin       coordinator
- Staff       volunteer
- 202681309   student (students log in with the 9 digits on a MUN card, not a name)

Why: the demo (app.demo) and the tests empty the TEST database every time, so
anything typed there is gone the next day. The working database is never
emptied, so these stay until someone deletes them.

Safe to run again: an account that's there already gets its password set back
to "Password" and is switched back on, and nothing is made twice.

Only for a database on this computer: it refuses any other, so these easy
passwords can never reach the real food bank's server.
"""

import sys

from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from app.config import config
from app.db import SessionLocal
from app.deps import get_now
from app.models import Staff
from app.services import accounts

PASSWORD = "Password"
COORDINATOR = "Admin"
VOLUNTEER = "Staff"
STUDENT_ID = "202681309"


def main() -> int:
    host = make_url(config.database_url).host
    if host not in ("localhost", "127.0.0.1", "::1"):
        print(f"The database is on {host}, not this computer. These accounts are for trying things locally only.")
        return 1

    now = get_now()
    with SessionLocal.begin() as db:
        accounts.food_bank_settings(db)  # refuses an empty database: run app.sample_data first
        admin = _coordinator(db, now)
        staff = _volunteer(db, admin, now)
        issued = accounts.give_student_setup_code(db, STUDENT_ID, staff, now)
        accounts.set_student_password(db, STUDENT_ID, issued.code, PASSWORD, None, now)

    print("Ready, in the working database (not emptied by the demo or the tests):")
    print(f"  {COORDINATOR:10} coordinator   password: {PASSWORD}")
    print(f"  {VOLUNTEER:10} volunteer     password: {PASSWORD}")
    print(f"  {STUDENT_ID:10} student       password: {PASSWORD}")
    return 0


def _coordinator(db, now) -> Staff:
    admin = _named(db, COORDINATOR)
    coordinators = db.scalars(select(Staff).where(Staff.role == "coordinator"))
    others = [s for s in coordinators if s.username.lower() != COORDINATOR.lower()]
    if admin is None and not others:
        issued = accounts.set_up_first_coordinator(db, COORDINATOR, now)
    else:
        if admin is None:
            admin, _ = accounts.add_volunteer(db, COORDINATOR, others[0], now)
        _switched_on(admin)
        if admin.role != "coordinator":
            admin.role = "coordinator"
        issued = accounts.give_volunteer_setup_code(db, admin, admin, now)
    return accounts.set_staff_password(db, COORDINATOR, issued.code, PASSWORD, None, now)


def _volunteer(db, admin: Staff, now) -> Staff:
    staff = _named(db, VOLUNTEER)
    if staff is None:
        staff, issued = accounts.add_volunteer(db, VOLUNTEER, admin, now)
    else:
        _switched_on(staff)
        issued = accounts.give_volunteer_setup_code(db, staff, admin, now)
    return accounts.set_staff_password(db, VOLUNTEER, issued.code, PASSWORD, None, now)


def _named(db, username: str) -> Staff | None:
    return db.scalar(select(Staff).where(func.lower(Staff.username) == username.lower()))


def _switched_on(staff: Staff) -> None:
    staff.disabled_at = None


if __name__ == "__main__":
    sys.exit(main())
