"""A load test: hundreds of students and volunteers using the real server at the same moment.

Run from backend/ (it empties the TEST database, like the tests and the demo do):

    .venv\\Scripts\\python -m loadtest.run
    .venv\\Scripts\\python -m loadtest.run --students 300 --capacity 20 --workers 4
    .venv\\Scripts\\python -m loadtest.run --one-core        (a small cloud server: 1 CPU)

It plays one pickup week, each phase with the server's clock moved to that moment:

1. Log-in rush. Sunday 4:59 pm: every student logs in at once.
2. Booking rush. 5:00 pm: booking opens and everyone tries to book at the same
   second. Some press Book twice, some use two phones, some cancel. Meanwhile a
   second group books Thursday, and the coordinator closes Thursday (snowstorm)
   in the middle of it.
3. Packing. Monday 12:05 pm: six volunteers pack every bag at once. A few bags
   are packed by two volunteers at the same moment on purpose.
4. Counter. Monday 3:31 pm: everyone arrives at once. Three volunteers hand
   over bags; some codes are typed at two counters at once, some with the wrong
   card. Students with no booking come as walk-ins, a few at two counters.
5. Jobs. Monday, 5 minutes after the no-show time: the jobs script runs twice at the same moment while
   volunteers use the pages.
6. A normal hour: people browsing for a while, to measure everyday speed.

After each phase it checks the database for broken rules (double bookings, a
slot over its places, food counted wrong, a bag handed over twice...) and that
the database agrees with what each person was told. Any 500 error, dropped
connection or broken rule is a bug and is listed at the end.
"""

import argparse
import asyncio
import os
import random
import re
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from datetime import time as clock

from app.config import BACKEND_DIR, config

if config.test_database_url == config.database_url:
    sys.exit("TEST_DATABASE_URL must point to a different database than DATABASE_URL, or the load test would empty it.")
config.database_url = config.test_database_url  # before app.db is imported

import httpx2 as httpx  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config as AlembicConfig  # noqa: E402
from sqlalchemy import create_engine, select, text  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.jobs import run_jobs  # noqa: E402
from app.models import PickupDay, Settings, Staff, Student, Variety  # noqa: E402
from app.sample_data import add_sample_data  # noqa: E402
from app.security.keyed_hash import id_hash  # noqa: E402
from app.security.passwords import hash_password  # noqa: E402
from app.services.pickup_days import NEWFOUNDLAND, make_pickup_day  # noqa: E402

PORT = 8077
BASE = f"http://127.0.0.1:{PORT}"
PASSWORD = "blue kettle on the stove"
LOG = BACKEND_DIR / "loadtest" / "server.log"
VOLUNTEERS = [f"Volunteer {n}" for n in range(1, 7)]
bugs: list[str] = []


def bug(message: str) -> None:
    bugs.append(message)
    print(f"  BUG: {message}")


# ---------- the dates ----------


def next_monday() -> date:
    """A Monday at least two days away, so its booking hasn't opened in real life."""
    today = datetime.now(NEWFOUNDLAND).date()
    monday = today + timedelta(days=(7 - today.weekday()) % 7)
    return monday if monday - today >= timedelta(days=2) else monday + timedelta(days=7)


MONDAY = next_monday()
THURSDAY = MONDAY + timedelta(days=3)


def nl(on: date, at: clock) -> datetime:
    return datetime.combine(on, at, tzinfo=NEWFOUNDLAND)


# ---------- the database ----------


def empty_test_database() -> None:
    fresh = create_engine(config.test_database_url)
    with fresh.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    fresh.dispose()
    alembic_config = AlembicConfig(BACKEND_DIR / "alembic.ini")
    alembic_config.set_main_option("sqlalchemy.url", config.test_database_url)
    command.upgrade(alembic_config, "head")


@dataclass
class World:
    monday_students: list[str]
    thursday_students: list[str]
    initial_stock: dict[int, int]
    capacity: int


def seed(students: int, thursday_students: int, capacity: int) -> World:
    """The sample food and settings, staff, and students who already have passwords.

    Every account gets the same argon2 hash, made once: hashing 300 passwords
    would only slow the setup down, and logging in still checks it for real.
    """
    empty_test_database()
    one_hash = hash_password(PASSWORD)
    week_ago = datetime.now(UTC) - timedelta(days=7)
    with SessionLocal.begin() as db:
        add_sample_data(db, week_ago)
        db.get(Settings, 1).slot_capacity = capacity
        alex = Staff(username="Alex", role="coordinator", password_hash=one_hash)
        db.add(alex)
        db.flush()
        for name in VOLUNTEERS:
            db.add(Staff(username=name, role="volunteer", password_hash=one_hash, created_by_staff_id=alex.id))
        numbers = [f"2026{n:05d}" for n in range(1, students + thursday_students + 1)]
        for number in numbers:
            db.add(Student(id_hash=id_hash(number), password_hash=one_hash, created_by_staff_id=alex.id))
        monday = make_pickup_day(db, MONDAY)
        thursday = make_pickup_day(db, THURSDAY)
        # Thursday opens at the same moment as Monday, so both are booked in the same rush.
        thursday.booking_opens_at = monday.booking_opens_at
        # A couple of foods with a bigger number, so many students fight over the same row.
        varieties = db.scalars(select(Variety).where(Variety.stock.is_not(None)).order_by(Variety.id)).all()
        for variety in varieties[:2]:
            variety.stock = 40
        db.flush()
        initial = {v.id: v.stock for v in db.scalars(select(Variety).where(Variety.stock.is_not(None)))}
    return World(numbers[:students], numbers[students:], initial, capacity)


def query(sql: str, **values) -> list:
    with engine.connect() as connection:
        return connection.execute(text(sql), values).all()


def check_the_rules(world: World, phase: str, walk_in_food: Counter, closed_thursday: bool) -> None:
    """Rules that must hold whatever happened at the same time."""
    print(f"  Checking the database after {phase}...")
    found = len(bugs)

    # A slot never has more bookings than places, and its count matches its bookings.
    for slot_id, capacity, booked_count, real in query(
        """SELECT s.id, s.capacity, s.booked_count,
                  (SELECT count(*) FROM bookings b WHERE b.slot_id = s.id AND b.status <> 'cancelled')
           FROM slots s"""
    ):
        if booked_count > capacity or booked_count < 0:
            bug(f"{phase}: slot {slot_id} has booked_count {booked_count} for {capacity} places")
        if booked_count != real:
            bug(f"{phase}: slot {slot_id} says {booked_count} booked, but has {real} bookings that aren't cancelled")

    # Active holds and bookings together never go over a slot's places.
    for slot_id, capacity, used in query(
        """SELECT s.id, s.capacity,
                  s.booked_count + (SELECT count(*) FROM holds h WHERE h.slot_id = s.id AND h.held_until > now())
           FROM slots s"""
    ):
        if used > capacity:
            bug(f"{phase}: slot {slot_id} has {used} bookings and live holds for {capacity} places")

    # One upcoming booking per student (F2), one booking per student per day.
    for student_id, n in query(
        "SELECT student_id, count(*) FROM bookings WHERE status IN ('booked', 'packed') GROUP BY student_id HAVING count(*) > 1"
    ):
        bug(f"{phase}: student {student_id} has {n} upcoming bookings")
    for student_id, day_id, n in query(
        "SELECT student_id, pickup_day_id, count(*) FROM bookings GROUP BY 1, 2 HAVING count(*) > 1"
    ):
        bug(f"{phase}: student {student_id} has {n} bookings on day {day_id}")
    for day_id, code, n in query("SELECT pickup_day_id, code, count(*) FROM bookings GROUP BY 1, 2 HAVING count(*) > 1"):
        bug(f"{phase}: code {code} is used {n} times on day {day_id}")

    # Food with a number: what's left + what's in live bookings + what walk-ins took = what we started with.
    held = defaultdict(int)
    for variety_id, quantity in query(
        """SELECT bi.variety_id, sum(bi.quantity) FROM booking_items bi JOIN bookings b ON b.id = bi.booking_id
           WHERE b.status IN ('booked', 'packed', 'picked_up') GROUP BY 1"""
    ):
        held[variety_id] = quantity
    for variety_id, stock in query("SELECT id, stock FROM varieties WHERE stock IS NOT NULL"):
        start = world.initial_stock.get(variety_id)
        if start is None:
            continue
        if stock < 0:
            bug(f"{phase}: variety {variety_id} has stock {stock}")
        accounted = stock + held[variety_id] + walk_in_food[variety_id]
        if accounted != start:
            bug(
                f"{phase}: variety {variety_id} started at {start}, now {stock} left + {held[variety_id]} booked "
                f"+ {walk_in_food[variety_id]} to walk-ins = {accounted}"
            )

    if closed_thursday:
        for (n,) in query(
            "SELECT count(*) FROM bookings b JOIN pickup_days d ON d.id = b.pickup_day_id "
            "WHERE d.pickup_date = :day AND b.status <> 'cancelled'",
            day=THURSDAY,
        ):
            if n:
                bug(f"{phase}: Thursday is closed but still has {n} live bookings")

    if len(bugs) == found:
        print("  All rules hold.")


# ---------- the server ----------


class Server:
    def __init__(self, workers: int, one_core: bool):
        self.workers, self.one_core = workers, one_core
        self.process: subprocess.Popen | None = None
        self.shift = timedelta(0)

    def now(self) -> datetime:
        """What the server's clock says right now."""
        return datetime.now(UTC) + self.shift

    def start(self, at: datetime) -> None:
        self.shift = at - datetime.now(UTC)
        env = os.environ | {"LOADTEST_SHIFT_SECONDS": str(self.shift.total_seconds())}
        args = [
            sys.executable, "-m", "uvicorn", "loadtest.serve:app",
            "--host", "127.0.0.1", "--port", str(PORT), "--workers", str(self.workers),
            "--log-level", "warning", "--no-access-log",
        ]  # fmt: skip
        if self.one_core:
            # cmd's start /affinity 1: the server and its workers may use one CPU core only.
            # The "" is the window title: without it, start takes the quoted python path as the title.
            args = ["cmd", "/c", "start", "", "/b", "/wait", "/affinity", "1", *args]
        log = open(LOG, "a", encoding="utf-8")
        log.write(f"\n===== server started, clock {at.astimezone(NEWFOUNDLAND):%a %d %b %H:%M:%S} =====\n")
        log.flush()
        self.process = subprocess.Popen(args, cwd=BACKEND_DIR, env=env, stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{BASE}/api/pickup-days", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.3)
        else:
            raise RuntimeError("The server didn't start. See loadtest/server.log")
        if self.workers > 1:
            self._wait_for_every_worker(deadline)

    def _wait_for_every_worker(self, deadline: float) -> None:
        """With several server processes, wait until all of them answer, not just the first.

        Found on 13 Nov: on Windows, a process still starting up already takes
        its share of new connections, and doesn't answer them. Right after the
        first answer, 41 of 200 requests timed out; 15 seconds later, all 200
        answered in under a second. A real server starts long before 5 pm, so
        the rush must not begin until every process is up.
        """

        def answers() -> bool:
            try:
                return httpx.get(f"{BASE}/api/pickup-days", timeout=3).status_code == 200
            except httpx.HTTPError:
                return False

        # Plain threads: this runs inside the load test's own event loop.
        with ThreadPoolExecutor(max_workers=10 * self.workers) as pool:
            while time.monotonic() < deadline:
                if all(pool.map(lambda _: answers(), range(10 * self.workers))):
                    return
        raise RuntimeError("Not every server process started. See loadtest/server.log")

    def memory(self) -> tuple[int, int]:
        """(largest peak of any server process, sum of peaks) in MB, from Windows."""
        script = f"""
$all = Get-CimInstance Win32_Process
$ids = @({self.process.pid})
do {{ $new = @($all | Where-Object {{ $ids -contains $_.ParentProcessId -and $ids -notcontains $_.ProcessId }} | ForEach-Object ProcessId); $ids += $new }} while ($new.Count)
$ids | ForEach-Object {{ $p = Get-Process -Id $_ -ErrorAction SilentlyContinue; if ($p -and $p.ProcessName -like 'python*') {{ $p.PeakWorkingSet64 }} }}
"""
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True).stdout
        peaks = [int(line) // 2**20 for line in out.split() if line.strip().isdigit()]
        return (max(peaks, default=0), sum(peaks))

    def stop(self) -> None:
        """Stop the server and every process under it.

        Found on 13 Nov: killing the tree from the top sometimes left uvicorn's
        worker processes running on their own, each holding its 15 database
        connections. Four of them used 60 of PostgreSQL's 100, and the next run
        failed for want of connections. So every process is listed first, from
        the top down, and each is stopped by its own id.
        """
        if self.process is None:
            return
        family = self._family()
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.process.pid)], capture_output=True)
        for pid in family:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        self.process.wait()
        self.process = None
        # A process can take a moment to really end on Windows. Until it has, it may
        # still answer requests with the last phase's clock (seen 13 Nov: the packing
        # queue was answered by a process still living on Sunday). So wait for each one.
        deadline = time.monotonic() + 20
        while (left := self._alive(family)) and time.monotonic() < deadline:
            for pid in left:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            time.sleep(0.5)
        if left:
            raise RuntimeError(f"Server processes still running 20 seconds after stopping: {left}")

    def _family(self) -> list[int]:
        """The server's process id and all its descendants', from Windows. Python processes only.

        Windows reuses process ids, so another program's "parent" can be an id
        that once belonged to the server (seen 13 Nov: an ASUS utility). The
        server and its workers are all Python, so nothing else is ever included.
        """
        script = f"""
$all = Get-CimInstance Win32_Process | Where-Object {{ $_.Name -like 'python*' }}
$ids = @({self.process.pid})
do {{ $new = @($all | Where-Object {{ $ids -contains $_.ParentProcessId -and $ids -notcontains $_.ProcessId }} | ForEach-Object ProcessId); $ids += $new }} while ($new.Count)
$ids
"""
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True).stdout
        return [int(line) for line in out.split() if line.strip().isdigit()]

    @staticmethod
    def _alive(pids: list[int]) -> list[int]:
        if not pids:
            return []
        script = f"@({','.join(map(str, pids))}) | ForEach-Object {{ if (Get-Process -Id $_ -ErrorAction SilentlyContinue) {{ $_ }} }}"
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True).stdout
        return [int(line) for line in out.split() if line.strip().isdigit()]


# ---------- people and requests ----------


class Stats:
    def __init__(self) -> None:
        self.rows: dict[str, list[tuple[float, str]]] = defaultdict(list)

    def add(self, name: str, ms: float, status: str) -> None:
        self.rows[name].append((ms, status))

    def report(self) -> None:
        print(f"    {'request':<28}{'sent':>6}{'ok':>6}{'refused':>9}{'5xx/fail':>9}{'median':>9}{'p95':>9}{'max':>9}")
        for name, rows in self.rows.items():
            times = sorted(ms for ms, _ in rows)
            ok = sum(1 for _, s in rows if s.startswith("2"))
            failed = [s for _, s in rows if s.startswith("5") or s.startswith("EXC")]
            refused = len(rows) - ok - len(failed)
            p95 = times[max(0, int(len(times) * 0.95) - 1)]
            print(
                f"    {name:<28}{len(rows):>6}{ok:>6}{refused:>9}{len(failed):>9}"
                f"{statistics.median(times):>8.0f}ms{p95:>7.0f}ms{times[-1]:>7.0f}ms"
            )
            for status, n in Counter(failed).items():
                bug(f"{name}: {n} x {status}")


@dataclass
class Person:
    name: str  # an ID number or a username
    client: httpx.AsyncClient
    second_phone: httpx.AsyncClient | None = None
    role: str = "normal"
    booked_code: str | None = None
    cancelled: bool = False
    picked_up: bool = False
    walked_in: bool = False
    outcome: str = ""


def new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=BASE, timeout=httpx.Timeout(120))


async def call(stats: Stats, client: httpx.AsyncClient, method: str, path: str, name: str, body=None):
    started = time.perf_counter()
    try:
        response = await client.request(method, path, json=body)
    except Exception as problem:  # a dropped connection or a timeout: the person got nothing
        stats.add(name, (time.perf_counter() - started) * 1000, f"EXC {type(problem).__name__}")
        return None
    stats.add(name, (time.perf_counter() - started) * 1000, str(response.status_code))
    return response


async def all_at_once(work) -> float:
    """Start every coroutine, then let them all go at the same moment. Returns the seconds it took."""
    go = asyncio.Event()

    async def wait_then(coroutine):
        await go.wait()
        return await coroutine

    tasks = [asyncio.create_task(wait_then(c)) for c in work]
    await asyncio.sleep(0.5)
    started = time.perf_counter()
    go.set()
    try:
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=900)
    except TimeoutError:
        bug("A phase was still going after 15 minutes, so it was stopped")
    return time.perf_counter() - started


def detail(response) -> str:
    try:
        return str(response.json().get("detail"))
    except Exception:
        return response.text[:100]


# ---------- 1 and 2: the log-in rush and the booking rush ----------


async def log_in_everyone(people: list[Person], stats: Stats) -> float:
    async def one(person: Person, client: httpx.AsyncClient):
        r = await call(stats, client, "POST", "/api/student/login", "student log in",
                       {"id_number": person.name, "password": PASSWORD})  # fmt: skip
        if r is None or r.status_code != 200:
            person.outcome = "couldn't log in"

    work = [one(p, p.client) for p in people] + [one(p, p.second_phone) for p in people if p.second_phone]
    return await all_at_once(work)


def choose_food(food: dict, rng: random.Random) -> tuple[list[dict], list[int]]:
    """Like a student: a handful of things, one kind of each, and a few substitutes."""
    items = [item for category in food["bookable"] for item in category["items"]]
    rng.shuffle(items)
    chosen, substitutes = [], []
    for item in items[: rng.randint(3, 9)]:
        kinds = [v for v in item["varieties"] if v["stock"] is None or v["stock"] > 0]
        if kinds:
            chosen.append({"variety_id": rng.choice(kinds)["id"], "quantity": 1})
    chosen_ids = {c["variety_id"] for c in chosen}
    spare = [v["id"] for item in items[9:] for v in item["varieties"] if v["id"] not in chosen_ids]
    substitutes = rng.sample(spare, min(len(spare), rng.randint(0, 3)))
    return chosen, substitutes


async def book_a_day(person: Person, pickup_date: date, stats: Stats, rng: random.Random, first_ready: asyncio.Event):
    client = person.client
    # Refresh until booking opens, like everyone does at 4:59 pm. An error page
    # gets refreshed too, but after 20 errors in a row they give up.
    errors = 0
    while True:
        r = await call(stats, client, "GET", "/api/pickup-days", "see pickup days")
        if r is None or r.status_code != 200:
            errors += 1
            if errors >= 20:
                person.outcome = "gave up: the times page kept failing"
                return
            await asyncio.sleep(rng.uniform(1, 3))
            continue
        errors = 0
        day = next(d for d in r.json() if d["pickup_date"] == pickup_date.isoformat())
        if day["booking_status"] == "open":
            break
        if day["booking_status"] == "day_closed":
            person.outcome = "day closed"
            return
        await asyncio.sleep(rng.uniform(0.7, 1.3))
    first_ready.set()

    # Hold a time. Most people go for one of the first free times.
    held = False
    for _ in range(8):
        free = [s for s in day["slots"] if s["places_left"] > 0]
        if not free:
            person.outcome = "no times left"
            return
        slot = rng.choice(free[:3])
        if person.role == "double":
            # Pressing the time twice.
            answers = await asyncio.gather(
                call(stats, client, "POST", "/api/holds", "hold a time", {"slot_id": slot["id"]}),
                call(stats, client, "POST", "/api/holds", "hold a time", {"slot_id": slot["id"]}),
            )
        elif person.role == "two phones":
            # The same student on two phones, choosing two different times at the same moment.
            other = rng.choice(free) if len(free) > 1 else slot
            answers = await asyncio.gather(
                call(stats, client, "POST", "/api/holds", "hold a time", {"slot_id": slot["id"]}),
                call(stats, person.second_phone, "POST", "/api/holds", "hold a time (2nd phone)", {"slot_id": other["id"]}),
            )
        else:
            answers = [await call(stats, client, "POST", "/api/holds", "hold a time", {"slot_id": slot["id"]})]
        if any(a is not None and a.status_code == 201 for a in answers):
            held = True
            break
        if any(a is not None and a.status_code != 409 for a in answers):
            person.outcome = f"hold refused: {detail(next(a for a in answers if a is not None and a.status_code != 409))}"
            return
        r = await call(stats, client, "GET", "/api/pickup-days", "see pickup days")
        if r is None or r.status_code != 200:
            return
        day = next(d for d in r.json() if d["pickup_date"] == pickup_date.isoformat())
    if not held:
        person.outcome = "kept losing the time"
        return

    r = await call(stats, client, "GET", "/api/food", "see the food")
    await call(stats, client, "GET", "/api/my-booking", "see my booking")
    if r is None or r.status_code != 200:
        return
    items, substitutes = choose_food(r.json(), rng)
    await asyncio.sleep(rng.uniform(2, 10))  # choosing food

    for _ in range(6):
        body = {"items": items, "substitutes": substitutes}
        if person.role in ("double", "two phones"):
            second = person.second_phone if person.role == "two phones" else client
            answers = await asyncio.gather(
                call(stats, client, "POST", "/api/bookings", "press Book", body),
                call(stats, second, "POST", "/api/bookings", "press Book (2nd tap)", body),
            )
            wins = [a for a in answers if a is not None and a.status_code == 201]
            if len(wins) > 1:
                bug(f"{person.name} pressed Book twice and got two bookings: {[w.json()['code'] for w in wins]}")
            answer = wins[0] if wins else next((a for a in answers if a is not None), None)
        else:
            answer = await call(stats, client, "POST", "/api/bookings", "press Book", body)
        if answer is None:
            person.outcome = "no answer to Book"
            return
        if answer.status_code == 201:
            person.booked_code = answer.json()["code"]
            person.outcome = "booked"
            break
        words = detail(answer)
        ran_out = re.match(r"Sorry, (.+) has just run out", words)
        if answer.status_code == 409 and ran_out:
            names = {v["id"]: v["name"] for c in r.json()["bookable"] for i in c["items"] for v in i["varieties"]}
            items = [c for c in items if names[c["variety_id"]] != ran_out.group(1)]
            if not items:
                person.outcome = "all chosen food ran out"
                await call(stats, client, "DELETE", "/api/holds", "let go of the time")
                return
            continue
        if answer.status_code == 409 and "booked already" in words:
            person.booked_code = re.search(r"code is (\w+)", words).group(1)
            person.outcome = "booked"
            break
        person.outcome = f"Book refused: {words}"
        return

    if person.booked_code and person.role == "cancels":
        await asyncio.sleep(rng.uniform(0, 3))
        answers = await asyncio.gather(  # and taps Cancel twice
            call(stats, client, "POST", "/api/my-booking/cancel", "cancel"),
            call(stats, client, "POST", "/api/my-booking/cancel", "cancel"),
        )
        if sum(1 for a in answers if a is not None and a.status_code == 204) != 1:
            bug(f"{person.name} tapped Cancel twice: answers {[a.status_code if a else None for a in answers]}")
        person.cancelled = True
        person.outcome = "booked, then cancelled"


async def booking_rush(server: Server, monday: list[Person], thursday: list[Person], coordinator: Person, stats: Stats):
    rng = random.Random(7)
    first_ready = asyncio.Event()

    async def close_thursday():
        try:
            await asyncio.wait_for(first_ready.wait(), timeout=90)
        except TimeoutError:
            bug("Nobody could see that booking had opened within 90 seconds")
        await asyncio.sleep(4)  # while lots of Thursday students are halfway through
        r = await call(stats, coordinator.client, "POST", f"/api/coordinator/days/{THURSDAY.isoformat()}/close", "coordinator closes a day",
                       {"reason": "Snow storm"})  # fmt: skip
        print(f"    Coordinator closed Thursday at {server.now().astimezone(NEWFOUNDLAND):%H:%M:%S}: {r.status_code if r else 'no answer'}")

    work = [book_a_day(p, MONDAY, stats, random.Random(rng.random()), first_ready) for p in monday]
    work += [book_a_day(p, THURSDAY, stats, random.Random(rng.random()), first_ready) for p in thursday]
    work.append(close_thursday())
    return await all_at_once(work)


# ---------- 3: packing ----------


async def pack_everything(volunteers: list[Person], stats: Stats) -> float:
    rng = random.Random(11)
    first = await call(stats, volunteers[0].client, "GET", "/api/packing", "packing queue")
    if first is None or first.status_code != 200 or "bags" not in first.json():
        # Say what came back, rather than stopping the whole run (seen once, 13 Nov).
        answer = "no answer" if first is None else f"{first.status_code} {first.text[:200]}"
        bug(f"The packing queue didn't list the bags: {answer}")
        return 0.0
    bags = [b for b in first.json()["bags"] if b["status"] == "booked"]
    clash = bags[:5]

    async def pack(volunteer: Person, bag_id: int, anyway: bool, label: str):
        c = volunteer.client
        r = await call(stats, c, "POST", f"/api/packing/bags/{bag_id}/start", "open a bag", {"anyway": anyway})
        if r is None or r.status_code != 200 or not r.json()["yours"]:
            return None
        await call(stats, c, "GET", f"/api/packing/bags/{bag_id}", "see a bag")
        plan = await call(stats, c, "POST", f"/api/packing/bags/{bag_id}/plan", "work out the bag", {"missing": [], "not_on_shelf": []})
        if plan is None or plan.status_code != 200:
            return None
        await asyncio.sleep(rng.uniform(0.2, 1.5))  # putting food in the bag
        body = {"missing": [], "not_on_shelf": [], "uses": plan.json()["uses"], "found": []}
        return await call(stats, c, "POST", f"/api/packing/bags/{bag_id}/packed", label, body)

    async def two_at_once(bag):
        # Two volunteers were both warned and both chose "Pack it anyway".
        a, b = rng.sample(volunteers, 2)
        answers = await asyncio.gather(pack(a, bag["id"], True, "press Packed"), pack(b, bag["id"], True, "press Packed"))
        oks = [x for x in answers if x is not None and x.status_code == 200]
        if len(oks) != 1:
            bug(f"Bag {bag['code']} packed by two volunteers at once: {[x.status_code if x else None for x in answers]} (want one 200)")

    async def volunteer_loop(volunteer: Person):
        while True:
            q = await call(stats, volunteer.client, "GET", "/api/packing", "packing queue")
            if q is None or q.status_code != 200:
                return
            todo = [b for b in q.json()["bags"] if b["status"] == "booked" and b["id"] not in {c["id"] for c in clash}
                    and (b["packing_by"] is None or b["packing_is_you"])]  # fmt: skip
            if not todo:
                return
            await pack(volunteer, rng.choice(todo[:4])["id"], False, "press Packed")

    return await all_at_once([two_at_once(b) for b in clash] + [volunteer_loop(v) for v in volunteers])


# ---------- 4: the counter ----------


async def counter_rush(students: list[Person], walk_ins: list[Person], volunteers: list[Person], stats: Stats,
                       walk_in_food: Counter, food: dict) -> float:  # fmt: skip
    rng = random.Random(13)
    coming = [p for p in students if p.booked_code and not p.cancelled]
    rng.shuffle(coming)
    coming = coming[: int(len(coming) * 0.85)]  # the rest won't come: no-shows at 6 pm
    clashes, wrong_card = coming[:5], coming[5:10]
    numbered = [(i["id"], v["id"]) for c in food["bookable"] for i in c["items"] for v in i["varieties"]
                if v["stock"] is not None and v["stock"] > 0]  # fmt: skip
    plain = [(i["id"], v["id"]) for c in food["bookable"] for i in c["items"] for v in i["varieties"][:1] if v["stock"] is None]

    async def hand_over(volunteer: Person, student: Person, id_number: str):
        c = volunteer.client
        await call(stats, c, "POST", "/api/counter/find", "find a bag", {"code": student.booked_code})
        return await call(stats, c, "POST", "/api/counter/pickups", "hand over a bag",
                          {"code": student.booked_code, "id_number": id_number})  # fmt: skip

    async def arrives(student: Person):
        if student in wrong_card:
            other = rng.choice([p for p in students if p is not student])
            r = await hand_over(rng.choice(volunteers), student, other.name)
            if r is not None and r.status_code == 201:
                bug(f"Bag {student.booked_code} was handed over with someone else's card")
        if student in clashes:
            a, b = rng.sample(volunteers, 2)
            answers = await asyncio.gather(hand_over(a, student, student.name), hand_over(b, student, student.name))
            oks = [x for x in answers if x is not None and x.status_code == 201]
            if len(oks) != 1:
                bug(f"Bag {student.booked_code} at two counters at once: {[x.status_code if x else None for x in answers]} (want one 201)")
            student.picked_up = bool(oks)
            return
        r = await hand_over(rng.choice(volunteers), student, student.name)
        student.picked_up = r is not None and r.status_code == 201
        if r is not None and r.status_code != 201:
            student.outcome = f"counter refused: {detail(r)}"

    async def walks_in(student: Person, twice: bool):
        picks = rng.sample(plain, min(3, len(plain)))
        food_list = [{"variety_id": v, "quantity": 1} for _, v in picks]
        # One food with a number too, from an item not picked yet (one of each item).
        spare = [(i, v) for i, v in numbered if i not in {i for i, _ in picks}]
        if spare:
            food_list.append({"variety_id": rng.choice(spare)[1], "quantity": 1})
        body = {"id_number": student.name, "never_in_old_system": True, "food": food_list, "extras": []}
        counters = rng.sample(volunteers, 2 if twice else 1)
        answers = await asyncio.gather(*(call(stats, v.client, "POST", "/api/walk-ins", "record a walk-in", body) for v in counters))
        oks = [x for x in answers if x is not None and x.status_code == 201]
        if len(oks) > 1:
            bug(f"Walk-in {student.name} served twice at two counters at once")
        if oks:
            student.walked_in = True
            for f in food_list:
                walk_in_food[f["variety_id"]] += f["quantity"]
        else:
            student.outcome = f"walk-in refused: {detail(next(a for a in answers if a is not None))}"

    work = [arrives(s) for s in coming] + [walks_in(s, i < 5) for i, s in enumerate(walk_ins)]
    return await all_at_once(work)


# ---------- 6: a normal hour ----------


async def normal_hour(students: list[Person], volunteers: list[Person], seconds: int, stats: Stats) -> int:
    rng = random.Random(17)
    stop_at = time.monotonic() + seconds
    sent = 0

    async def browse(person: Person, pages: list[str]):
        nonlocal sent
        while time.monotonic() < stop_at:
            page = rng.choice(pages)
            await call(stats, person.client, "GET", page, f"browse {page}")
            sent += 1
            await asyncio.sleep(rng.uniform(1, 4))

    student_pages = ["/api/pickup-days", "/api/food", "/api/my-booking", "/api/me"]
    staff_pages = ["/api/packing", "/api/counter", "/api/stock"]
    await asyncio.gather(*(browse(p, student_pages) for p in students), *(browse(v, staff_pages) for v in volunteers))
    return sent


# ---------- the whole week ----------


def say(moment: datetime) -> str:
    return moment.astimezone(NEWFOUNDLAND).strftime("%a %d %b %I:%M %p")


async def staff_log_in(names: list[str], stats: Stats) -> list[Person]:
    people = [Person(name, new_client()) for name in names]
    answers = await asyncio.gather(*(call(stats, p.client, "POST", "/api/staff/login", "staff log in",
                                          {"username": p.name, "password": PASSWORD}) for p in people))  # fmt: skip
    for person, answer in zip(people, answers):
        if answer is None or answer.status_code != 200:
            bug(f"{person.name} couldn't log in: {'no answer' if answer is None else f'{answer.status_code} {answer.text[:200]}'}")
    return people


def phase_end(server: Server, stats: Stats, seconds: float, label: str) -> None:
    stats.report()
    peak, total = server.memory()
    print(f"    Took {seconds:.1f} s. Server memory: biggest process peaked at {peak} MB ({total} MB all processes).")


async def main(args) -> int:
    LOG.write_text("", encoding="utf-8")
    print(f"Setting up: {args.students} students for Monday {MONDAY}, {args.thursday} for Thursday {THURSDAY}, "
          f"{args.capacity} place(s) per 10-minute slot (12 slots a day).")  # fmt: skip
    world = seed(args.students, args.thursday, args.capacity)
    server = Server(args.workers, args.one_core)
    print(f"Server: {args.workers} worker(s){', ONE CPU core' if args.one_core else ''}, the app's own database pool.")
    walk_in_food: Counter = Counter()
    rng = random.Random(3)

    monday = [Person(n, new_client()) for n in world.monday_students]
    thursday = [Person(n, new_client()) for n in world.thursday_students]
    for i, p in enumerate(monday):
        p.role = "double" if i % 10 == 3 else "cancels" if i % 15 == 7 else "normal"
    for p in rng.sample([p for p in monday if p.role == "normal"], 10):
        p.role, p.second_phone = "two phones", new_client()

    try:
        # 1 and 2.
        opens = nl(MONDAY - timedelta(days=1), clock(17, 0))
        server.start(opens - timedelta(seconds=25))
        print(f"\n1. Log-in rush, {say(server.now())}: every student logs in at the same moment")
        stats = Stats()
        coordinator = (await staff_log_in(["Alex"], stats))[0]
        seconds = await log_in_everyone(monday + thursday, stats)
        phase_end(server, stats, seconds, "log in")

        print(f"\n2. Booking rush: booking opens at {say(opens)}. Everyone is refreshing, then books at once.")
        print(f"   ({sum(p.role == 'double' for p in monday)} press everything twice, 10 use two phones, "
              f"{sum(p.role == 'cancels' for p in monday)} cancel; the coordinator closes Thursday partway.)")  # fmt: skip
        stats = Stats()
        seconds = await booking_rush(server, monday, thursday, coordinator, stats)
        phase_end(server, stats, seconds, "booking")
        outcomes = Counter(p.outcome for p in monday)
        print("    Monday outcomes: " + ", ".join(f"{n} {o}" for o, n in outcomes.most_common()))
        print("    Thursday outcomes: " + ", ".join(f"{n} {o}" for o, n in Counter(p.outcome for p in thursday).most_common()))
        check_the_rules(world, "the booking rush", walk_in_food, closed_thursday=True)

        # What each student was told agrees with the database.
        told_booked = {p.booked_code for p in monday if p.booked_code and not p.cancelled}
        in_db = {code for (code,) in query(
            "SELECT b.code FROM bookings b JOIN pickup_days d ON d.id = b.pickup_day_id "
            "WHERE d.pickup_date = :day AND b.status = 'booked'", day=MONDAY)}  # fmt: skip
        if told_booked != in_db:
            bug(f"Students told 'booked' ({len(told_booked)}) don't match the database ({len(in_db)}): "
                f"{sorted(told_booked ^ in_db)[:10]}")  # fmt: skip
        else:
            print(f"  Every one of the {len(in_db)} students told 'booked' has a booking, and nobody else does.")
        server.stop()

        # 3.
        server.start(nl(MONDAY, clock(12, 5)))
        print(f"\n3. Packing, {say(server.now())}: six volunteers pack every bag at once (5 bags by two at the same moment)")
        stats = Stats()
        volunteers = await staff_log_in(VOLUNTEERS, stats)
        seconds = await pack_everything(volunteers, stats)
        phase_end(server, stats, seconds, "packing")
        left = query("SELECT count(*) FROM bookings b JOIN pickup_days d ON d.id = b.pickup_day_id "
                     "WHERE d.pickup_date = :day AND b.status = 'booked'", day=MONDAY)[0][0]  # fmt: skip
        if left:
            bug(f"{left} Monday bags are still not packed")
        check_the_rules(world, "packing", walk_in_food, closed_thursday=True)
        server.stop()

        # 4.
        server.start(nl(MONDAY, clock(15, 31)))
        print(f"\n4. Counter, {say(server.now())}: everyone arrives at once, three volunteers at the counter")
        no_booking = [p for p in monday if not p.booked_code or p.cancelled]
        walk_ins = rng.sample(no_booking, min(30, len(no_booking)))
        print(f"   (5 codes typed at two counters at once, 5 tried with the wrong card first, {len(walk_ins)} walk-ins, 5 of them at two counters)")
        stats = Stats()
        food = (await call(stats, volunteers[0].client, "GET", "/api/food", "see the food")).json()
        seconds = await counter_rush(monday, walk_ins, volunteers[:3], stats, walk_in_food, food)
        phase_end(server, stats, seconds, "counter")
        told = {p.booked_code for p in monday if p.picked_up}
        in_db = {code for (code,) in query(
            "SELECT b.code FROM bookings b JOIN pickup_days d ON d.id = b.pickup_day_id "
            "WHERE d.pickup_date = :day AND b.status = 'picked_up'", day=MONDAY)}  # fmt: skip
        if told != in_db:
            bug(f"Bags volunteers were told were handed over ({len(told)}) don't match the database ({len(in_db)})")
        else:
            print(f"  {len(in_db)} bags handed over, each exactly once, matching what the volunteers were told.")
        walked = query("SELECT student_id, count(*) FROM walk_ins GROUP BY 1")
        for student_id, n in walked:
            if n > 1:
                bug(f"Student {student_id} has {n} walk-ins on one day")
        print(f"  {len(walked)} walk-ins recorded ({sum(p.walked_in for p in walk_ins)} told yes).")
        check_the_rules(world, "the counter", walk_in_food, closed_thursday=True)

        # 5.
        # 5 minutes after Monday's no-show time, whatever the settings say (8 pm since 13 Nov).
        with SessionLocal() as db:
            no_show_at = db.scalar(select(PickupDay.no_show_at).where(PickupDay.pickup_date == MONDAY))
        jobs_at = no_show_at + timedelta(minutes=5)
        server.stop()
        server.start(jobs_at)
        print(f"\n5. Jobs, {say(server.now())}: the jobs script runs twice at the same moment, while volunteers use the pages")
        stats = Stats()
        reports = []
        threads = [threading.Thread(target=lambda: reports.append(run_jobs(engine, server.now()))) for _ in range(2)]
        expected = query("SELECT count(*) FROM bookings b JOIN pickup_days d ON d.id = b.pickup_day_id "
                         "WHERE d.pickup_date = :day AND b.status = 'packed'", day=MONDAY)[0][0]  # fmt: skip
        started = time.perf_counter()
        for t in threads:
            t.start()
        await asyncio.gather(*(call(stats, v.client, "GET", page, f"browse {page}")
                               for v in volunteers for page in ("/api/packing", "/api/counter", "/api/stock")))  # fmt: skip
        for t in threads:
            t.join()
        phase_end(server, stats, time.perf_counter() - started, "jobs")
        for report in reports:
            print(f"    Jobs run: {report.no_shows} no-shows, skipped: {report.skipped or 'no'}, problems: {report.problems or 'none'}")
            for problem in report.problems:
                bug(f"jobs: {problem}")
        marked = sum(r.no_shows for r in reports)
        if marked != expected:
            bug(f"{expected} bags weren't collected, but the jobs marked {marked} no-shows")
        else:
            print(f"  {marked} uncollected bags became no-shows exactly once, and their food went back once.")
        check_the_rules(world, "the jobs", walk_in_food, closed_thursday=True)
        server.stop()

        # 6.
        if args.browse_seconds:
            server.start(nl(MONDAY, clock(19, 0)))
            print(f"\n6. A normal hour: {len(monday)} students and {len(volunteers)} volunteers browse for {args.browse_seconds} s")
            stats = Stats()
            started = time.perf_counter()
            sent = await normal_hour(monday, volunteers, args.browse_seconds, stats)
            took = time.perf_counter() - started
            phase_end(server, stats, took, "browse")
            print(f"    {sent / took:.0f} requests a second on average.")
    finally:
        server.stop()

    log = LOG.read_text(encoding="utf-8", errors="replace")
    errors = Counter(line.strip() for line in log.splitlines() if re.match(r"^\w+(\.\w+)*(Error|Exception|Violation)\b", line.strip()))
    if errors:
        print("\nErrors in the server log (loadtest/server.log):")
        for line, n in errors.most_common(10):
            print(f"  {n} x {line[:200]}")

    print("\n" + ("=" * 70))
    if bugs:
        print(f"{len(bugs)} PROBLEM(S) FOUND:")
        for b in bugs:
            print(f"  - {b}")
    else:
        print("No problems: no 500s, no dropped connections, every rule held.")
    return 1 if bugs else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--students", type=int, default=300, help="students who try to book Monday")
    parser.add_argument("--thursday", type=int, default=60, help="students who try to book Thursday, which gets closed")
    parser.add_argument("--capacity", type=int, default=1, help="places per 10-minute slot (the food bank's setting is 1)")
    parser.add_argument("--workers", type=int, default=1, help="server processes")
    parser.add_argument("--one-core", action="store_true", help="let the server use one CPU core, like a small cloud server")
    parser.add_argument("--browse-seconds", type=int, default=30, help="how long the normal hour lasts (0 to skip)")
    sys.stdout.reconfigure(line_buffering=True)
    sys.exit(asyncio.run(main(parser.parse_args())))
