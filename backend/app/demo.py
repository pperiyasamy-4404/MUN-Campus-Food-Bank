"""A demo of the whole system, with made-up students, on a busy pickup afternoon.

Run from backend/:

    .venv\\Scripts\\python -m app.demo

then open http://localhost:8000 and log in with one of the accounts it prints.

What it does:
1. Empties the TEST database and builds the tables again. The tests empty that
   database every run anyway, so nothing real is ever lost. The working
   database is never touched.
2. Fills it with the sample food and settings, and a few made-up students.
3. Sets the server's clock to the next Thursday at 4:00 pm, St. John's time,
   and lets it run on from there. At that moment packing, the counter and
   walk-ins are all open, so every page has something on it.
4. Serves the website (frontend/dist) and the server together on port 8000.

The story it sets up (one password for everyone, printed at the start):
- Last Monday is over: student 202300004 picked up, 202300006 didn't come.
- Today, Thursday: 202300001's bag is packed and ready to hand over, 202300002's
  was packed one item short, and 202300003's still has to be packed.
- Next Monday: Alex opened booking early, so 202300005 can book right now.
- Alex is the coordinator and Sam a volunteer.

Nothing runs the jobs script here, so the 6 pm no-show stays undone unless you
run it yourself. Stop the demo with Ctrl+C. Run it again for a fresh start.
"""

import sys
from datetime import UTC, date, datetime, time, timedelta

from app.config import BACKEND_DIR, config

if config.test_database_url == config.database_url:
    sys.exit("TEST_DATABASE_URL must point to a different database than DATABASE_URL, or the demo would empty it.")
# Before app.db is imported, so every session the demo and the server open uses the test database.
config.database_url = config.test_database_url
# The demo is plain http on this computer. Browsers allow that for localhost even
# with secure cookies, but this keeps the login working on 127.0.0.1 too.
config.cookie_secure = False

from alembic import command  # noqa: E402
from alembic.config import Config as AlembicConfig  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from sqlalchemy import create_engine, select, text  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.deps import get_now  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Slot, Student, Variety  # noqa: E402
from app.sample_data import add_sample_data  # noqa: E402
from app.services import accounts, counter, day_changes, no_shows, packing  # noqa: E402
from app.services import booking as booking_rules  # noqa: E402
from app.services.booking import Choice  # noqa: E402
from app.services.packing import Missing  # noqa: E402
from app.services.pickup_days import NEWFOUNDLAND, make_days_ahead, make_pickup_day  # noqa: E402

PASSWORD = "blue kettle on the stove"
FRONTEND = BACKEND_DIR.parent / "frontend" / "dist"
THURSDAY = 4  # isoweekday


def next_thursday_4pm(now: datetime) -> datetime:
    """The coming Thursday at 4:00 pm in St. John's (today, if today is a Thursday)."""
    today = now.astimezone(NEWFOUNDLAND).date()
    thursday = today + timedelta(days=(THURSDAY - today.isoweekday()) % 7)
    return datetime.combine(thursday, time(16, 0), tzinfo=NEWFOUNDLAND)


def empty_test_database() -> None:
    """Drop every table in the test database and build them again from the migrations."""
    engine = create_engine(config.test_database_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    alembic_config = AlembicConfig(BACKEND_DIR / "alembic.ini")
    alembic_config.set_main_option("sqlalchemy.url", config.test_database_url)
    command.upgrade(alembic_config, "head")


def fill(now: datetime) -> dict[str, str]:
    """Everything in the story above. Returns the codes of today's bags, by ID number."""
    thursday = now.astimezone(NEWFOUNDLAND).date()
    last_monday = thursday - timedelta(days=3)
    week_ago = now - timedelta(days=7)

    with SessionLocal.begin() as db:
        add_sample_data(db, week_ago)
        issued = accounts.set_up_first_coordinator(db, "Alex", week_ago)
        alex = accounts.set_staff_password(db, "Alex", issued.code, PASSWORD, None, week_ago)
        sam, issued = accounts.add_volunteer(db, "Sam", alex, week_ago)
        accounts.set_staff_password(db, "Sam", issued.code, PASSWORD, None, week_ago)
        variety = {v.name: v.id for v in db.scalars(select(Variety))}

        def student(id_number: str) -> Student:
            """A student whose ID card Sam checked a week ago (R1)."""
            issued = accounts.give_student_setup_code(db, id_number, sam, week_ago)
            return accounts.set_student_password(db, id_number, issued.code, PASSWORD, None, week_ago)

        def book(who: Student, day, food: list[str], substitutes: tuple[str, ...] = ()):
            """Book the first free slot, 5 minutes after booking opened."""
            free = db.scalars(
                select(Slot).where(Slot.pickup_day_id == day.id, Slot.booked_count == 0).order_by(Slot.starts_at)
            ).first()
            when = day.booking_opens_at + timedelta(minutes=5)
            booking_rules.hold_slot(db, who, free.id, when)
            return booking_rules.book(db, who, [Choice(variety[n]) for n in food], [variety[n] for n in substitutes], when)

        # Last Monday, over: one picked up, one didn't come.
        monday = make_pickup_day(db, last_monday)
        came = book(student("202300004"), monday, ["Smooth peanut butter", "Brown rice"])
        stayed_away = book(student("202300006"), monday, ["Corn flakes"])
        for bag in (came, stayed_away):
            packing.pack(db, bag.id, [], [], [], sam, monday.booking_closes_at + timedelta(minutes=10))
        counter.hand_over(db, came.code, "202300004", [], [], sam, monday.pickup_starts_at + timedelta(minutes=5))
        no_shows.mark_no_show(db, stayed_away.id, monday.no_show_at)

        # Today: one bag ready, one packed short, one still to pack.
        today = make_pickup_day(db, thursday)
        ready = book(student("202300001"), today, ["Quick oats", "Spaghetti", "Chunk chicken", "Corn flakes"], ("White rice",))
        short = book(student("202300002"), today, ["Steel-cut oats", "Sunflower oil", "Tuna in water"])
        to_pack = book(student("202300003"), today, ["Gluten-free pasta", "Vegetable oil"], ("White rice",))
        packing.pack(db, ready.id, [], [], [], sam, today.booking_closes_at + timedelta(minutes=30))
        packing.pack(db, short.id, [Missing(variety["Sunflower oil"])], [], [], sam, today.booking_closes_at + timedelta(minutes=35))

        # The coming week, as the jobs script would make it, with Monday's booking opened early (S9).
        next_monday = thursday + timedelta(days=4)
        make_days_ahead(db, now)
        day_changes.move_booking_times(
            db,
            next_monday,
            now - timedelta(minutes=5),
            datetime.combine(next_monday, time(12, 0), tzinfo=NEWFOUNDLAND),
            alex,
            now - timedelta(minutes=5),
        )
        student("202300005")  # no booking yet

        return {"202300001": ready.code, "202300002": short.code, "202300003": to_pack.code}


def serve_the_website() -> None:
    """Send the built React pages for every address that isn't /api, like the dev server does."""
    if not (FRONTEND / "index.html").is_file():
        print("No built website in frontend/dist. Run 'npm run build' in frontend/, or 'npm run dev' and use port 5173.")
        return

    @app.get("/{path:path}", include_in_schema=False)
    def page(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        file = (FRONTEND / path).resolve()
        if path and file.is_file() and FRONTEND in file.parents:
            return FileResponse(file)
        # /book, /packing and the rest are React pages: index.html shows the right one.
        return FileResponse(FRONTEND / "index.html")


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)  # show each line at once, even when the output goes to a file
    start = next_thursday_4pm(datetime.now(UTC))
    shift = start - datetime.now(UTC)

    def demo_now() -> datetime:
        return datetime.now(UTC) + shift

    print("Emptying the test database and filling it with the demo...")
    empty_test_database()
    codes = fill(demo_now())

    app.dependency_overrides[get_now] = demo_now
    serve_the_website()

    print()
    print(f"The demo clock says {start:%A %d %B}, 4:00 pm in St. John's, and runs on from there.")
    print(f"Password for every account: {PASSWORD}")
    print("  Alex        coordinator")
    print("  Sam         volunteer (packing, counter, setup codes)")
    print(f"  202300001   student, bag ready to hand over (code {codes['202300001']})")
    print(f"  202300002   student, bag packed one item short (code {codes['202300002']})")
    print(f"  202300003   student, bag still to pack (code {codes['202300003']})")
    print("  202300005   student, can book next Monday")
    print("  202300004   student, picked up last Monday (so can't book for 30 days)")
    print()
    print("Open http://localhost:8000   (Ctrl+C stops it)")

    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
