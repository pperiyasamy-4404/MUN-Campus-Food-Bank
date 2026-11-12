"""No-shows (B3, I6) and fixing a pickup marked wrong (B6), straight from app/services/no_shows.py.

The pickup day is Monday 9 November 2026: booking closes at 12 pm, pickup is
3:30 to 5:30 pm and no-shows are at 6 pm, St. John's time (UTC-3:30 in November).
The web side is in test_fixes_api.py.
"""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Booking,
    BookingItem,
    Category,
    CounterItem,
    Item,
    PickupDay,
    Settings,
    Slot,
    Staff,
    Student,
    Variety,
    WalkIn,
)
from app.problems import Problem
from app.sample_data import SAMPLE_SETTINGS
from app.security.keyed_hash import id_hash
from app.services import booking as booking_rules
from app.services import counter, no_shows, packing
from app.services.booking import Choice
from app.services.no_shows import CantFix
from app.services.packing import Missing
from app.services.pickup_days import make_pickup_day
from tests.helpers import ID_NUMBER, MONDAY, add, make_day, make_staff, wait_until_someone_is_waiting_for_a_lock

OPEN = datetime(2026, 11, 8, 21, 0, tzinfo=UTC)  # Sunday 5:30 pm: booking for Monday is open
PACKING = datetime(2026, 11, 9, 16, 0, tzinfo=UTC)  # Monday 12:30 pm
COUNTER = datetime(2026, 11, 9, 19, 10, tzinfo=UTC)  # Monday 3:40 pm
NO_SHOW = datetime(2026, 11, 9, 21, 30, tzinfo=UTC)  # Monday 6:00 pm
AFTER = datetime(2026, 11, 9, 21, 45, tzinfo=UTC)  # Monday 6:15 pm
A_MOMENT = timedelta(microseconds=1)


# ---------- the world ----------


@pytest.fixture
def monday(db_with_sample_week) -> PickupDay:
    return make_pickup_day(db_with_sample_week, MONDAY)


@pytest.fixture
def food(db_with_sample_week) -> dict[str, Variety]:
    """5 of each, and bread as an extra."""
    db = db_with_sample_week
    pantry = add(db, Category(name="Pantry"))

    def variety(item_name: str, name: str, is_extra: bool = False) -> Variety:
        item = add(db, Item(name=item_name, category_id=pantry.id, is_extra=is_extra))
        return add(db, Variety(item_id=item.id, name=name, stock=5))

    return {
        "quick oats": variety("Oats", "Quick oats"),
        "sunflower oil": variety("Cooking oil", "Sunflower oil"),
        "rice": variety("Rice", "White rice"),
        "lentils": variety("Lentils", "Red lentils"),
        "white bread": variety("Bread", "White bread", is_extra=True),
    }


@pytest.fixture
def sam(db_with_sample_week) -> Staff:
    return make_staff(db_with_sample_week, "Sam")


@pytest.fixture
def student(db_with_sample_week) -> Student:
    """The student whose MUN card has ID_NUMBER."""
    db = db_with_sample_week
    return add(db, Student(id_hash=id_hash(ID_NUMBER), created_by_staff_id=make_staff(db).id))


def booked(db, day, student, food, *names, substitutes=()) -> Booking:
    """Booked on Sunday, in the day's first free time."""
    free = db.scalars(
        select(Slot).where(Slot.pickup_day_id == day.id, Slot.booked_count == 0).order_by(Slot.starts_at)
    ).first()
    booking_rules.hold_slot(db, student, free.id, OPEN)
    return booking_rules.book(db, student, [Choice(food[n].id) for n in names], [food[n].id for n in substitutes], OPEN)


def packed(db, day, student, food, *names, missing=(), substitutes=(), uses=()) -> Booking:
    """Booked on Sunday, packed on Monday at 12:30."""
    bag = booked(db, day, student, food, *names, substitutes=substitutes)
    packing.pack(db, bag.id, [Missing(food[n].id) for n in missing], [], [food[n].id for n in uses], make_staff(db), PACKING)
    return bag


def stock(food) -> dict[str, int]:
    return {name: variety.stock for name, variety in food.items()}


def refused(db, kind, call):
    """Expect a refusal, and undo whatever the call did, the way the route's missing commit would."""
    with pytest.raises(kind) as refusal:
        with db.begin_nested():
            call()
    return refusal.value


# ---------- the no-show job (B3, I6) ----------


def test_a_packed_bag_not_picked_up_becomes_a_no_show_at_6_pm(db, monday, food, student):
    bag = packed(db, monday, student, food, "quick oats", "rice")

    assert no_shows.due_no_shows(db, NO_SHOW) == [bag.id]
    assert no_shows.mark_no_show(db, bag.id, NO_SHOW) is bag

    # The day's no-show time, even if the job runs later.
    assert (bag.status, bag.no_show_at) == ("no_show", NO_SHOW)
    # Back on the shelf: booking took 1 of each, the no-show gives it back.
    assert stock(food) == {"quick oats": 5, "sunflower oil": 5, "rice": 5, "lentils": 5, "white bread": 5}


def test_a_late_run_saves_the_days_no_show_time(db, monday, food, student):
    bag = packed(db, monday, student, food, "quick oats")

    no_shows.mark_no_show(db, bag.id, NO_SHOW + timedelta(hours=14))

    assert bag.no_show_at == NO_SHOW


def test_nothing_is_a_no_show_before_6_pm(db, monday, food, student):
    bag = packed(db, monday, student, food, "quick oats")

    assert no_shows.due_no_shows(db, NO_SHOW - A_MOMENT) == []
    assert no_shows.mark_no_show(db, bag.id, NO_SHOW - A_MOMENT) is None
    assert bag.status == "packed"


def test_a_bag_never_packed_gives_back_what_was_booked(db, monday, food, student):
    bag = booked(db, monday, student, food, "quick oats", "sunflower oil", substitutes=["lentils"])
    assert stock(food)["quick oats"] == 4

    no_shows.mark_no_show(db, bag.id, NO_SHOW)

    # Substitutes were never taken off stock (U3), so nothing comes back for them.
    assert stock(food) == {"quick oats": 5, "sunflower oil": 5, "rice": 5, "lentils": 5, "white bread": 5}


def test_a_packed_bag_gives_back_what_was_really_in_it(db, monday, food, student):
    """The oil wasn't on the shelf, so lentils went in instead (U4). The oil
    never went in the bag, so it doesn't come back. The lentils do."""
    bag = packed(
        db, monday, student, food, "quick oats", "sunflower oil", substitutes=["lentils"], missing=["sunflower oil"], uses=["lentils"]
    )
    before = stock(food)

    no_shows.mark_no_show(db, bag.id, NO_SHOW)

    after = stock(food)
    assert after["quick oats"] == before["quick oats"] + 1
    assert after["lentils"] == before["lentils"] + 1
    assert after["sunflower oil"] == before["sunflower oil"]


def test_picked_up_and_cancelled_bookings_are_left_alone(db, monday, food, student, sam):
    bag = packed(db, monday, student, food, "quick oats")
    counter.hand_over(db, bag.code, ID_NUMBER, [], [], sam, COUNTER)

    assert no_shows.due_no_shows(db, NO_SHOW) == []
    assert no_shows.mark_no_show(db, bag.id, NO_SHOW) is None
    assert bag.status == "picked_up"


def test_a_closed_day_has_no_no_shows(db, monday, food, student):
    """Closing a day cancels its bookings (S7, step 9). Nobody is a no-show on a day the food bank closed."""
    bag = packed(db, monday, student, food, "quick oats")
    monday.closed_at, monday.closed_reason = PACKING, "Snow day"
    db.flush()

    assert no_shows.due_no_shows(db, NO_SHOW) == []
    assert no_shows.mark_no_show(db, bag.id, NO_SHOW) is None


def test_a_no_show_happens_once(db, monday, food, student):
    bag = packed(db, monday, student, food, "quick oats")
    no_shows.mark_no_show(db, bag.id, NO_SHOW)

    assert no_shows.due_no_shows(db, AFTER) == []
    assert no_shows.mark_no_show(db, bag.id, AFTER) is None
    # Given back once, not twice.
    assert food["quick oats"].stock == 5


# ---------- fixing a mistake afterwards (B6) ----------


def test_a_no_show_that_was_handed_over_is_fixed_to_picked_up(db, monday, food, student, sam):
    bag = packed(db, monday, student, food, "quick oats", "rice")
    no_shows.mark_no_show(db, bag.id, NO_SHOW)

    no_shows.fix_to_picked_up(db, bag.id, sam, AFTER)

    assert (bag.status, bag.no_show_at, bag.picked_up_at, bag.picked_up_by_staff_id) == ("picked_up", None, AFTER, sam.id)
    # The food left with the student, so it comes off the shelf again.
    assert (food["quick oats"].stock, food["rice"].stock) == (4, 4)
    # F1: the 28 days count from Monday.
    assert student.last_pickup_on == MONDAY
    logged = db.scalar(select(AuditLog).where(AuditLog.action == "fixed_no_show_to_picked_up"))
    assert (logged.staff_id, logged.booking_id, logged.student_id) == (sam.id, bag.id, student.id)


def test_a_fix_takes_no_more_than_the_shelf_has(db, monday, food, student, sam):
    """Someone counted the shelf after the no-show: there are none. The count can't go below none."""
    bag = packed(db, monday, student, food, "quick oats")
    no_shows.mark_no_show(db, bag.id, NO_SHOW)
    food["quick oats"].stock = 0

    no_shows.fix_to_picked_up(db, bag.id, sam, AFTER)

    assert food["quick oats"].stock == 0


def test_a_bag_never_packed_cant_have_been_handed_over(db, monday, food, student, sam):
    bag = booked(db, monday, student, food, "quick oats")
    no_shows.mark_no_show(db, bag.id, NO_SHOW)

    problem = refused(db, Problem, lambda: no_shows.fix_to_picked_up(db, bag.id, sam, AFTER))

    assert problem.message == f"Bag {bag.code} was never packed, so it can't have been handed over."


def test_fixes_wait_until_the_day_is_over(db, monday, food, student, sam):
    bag = packed(db, monday, student, food, "quick oats")
    counter.hand_over(db, bag.code, ID_NUMBER, [], [], sam, COUNTER)

    problem = refused(db, Problem, lambda: no_shows.fix_to_no_show(db, bag.id, sam, NO_SHOW - A_MOMENT))

    assert problem.message == "Pickups for Monday, November 9 can be fixed once the day is over, at 6:00 p.m."


def test_a_bag_marked_picked_up_by_mistake_is_fixed_to_no_show(db, monday, food, student, sam):
    """Everything recorded as handed over goes back on the shelf, the bread from the counter too."""
    bag = packed(db, monday, student, food, "quick oats", "rice")
    counter.hand_over(db, bag.code, ID_NUMBER, [], [food["white bread"].id], sam, COUNTER)
    lee = make_staff(db, "Lee")

    no_shows.fix_to_no_show(db, bag.id, lee, AFTER)

    assert (bag.status, bag.no_show_at, bag.picked_up_at, bag.picked_up_by_staff_id) == ("no_show", NO_SHOW, None, None)
    assert stock(food) == {"quick oats": 5, "sunflower oil": 5, "rice": 5, "lentils": 5, "white bread": 5}
    assert db.scalar(select(func.count()).select_from(CounterItem).where(CounterItem.booking_id == bag.id)) == 0
    # No other pickup on record, so the 28 days don't apply any more.
    assert student.last_pickup_on is None
    assert booking_rules.next_pickup_allowed_on(db, student, db.get(Settings, 1)) is None
    # The log keeps both: who marked it picked up, and who fixed it.
    actions = db.execute(select(AuditLog.action, AuditLog.staff_id).where(AuditLog.booking_id == bag.id).order_by(AuditLog.id))
    assert actions.all() == [("marked_picked_up", sam.id), ("fixed_picked_up_to_no_show", lee.id)]


def test_fixing_to_no_show_keeps_an_earlier_pickup_on_record(db, monday, food, student, sam):
    four_weeks_ago = make_day(db, MONDAY - timedelta(days=28))
    add(db, WalkIn(student_id=student.id, pickup_day_id=four_weeks_ago.id, served_at=COUNTER - timedelta(days=28), served_by_staff_id=sam.id))
    bag = packed(db, monday, student, food, "quick oats")
    counter.hand_over(db, bag.code, ID_NUMBER, [], [], sam, COUNTER)

    no_shows.fix_to_no_show(db, bag.id, sam, AFTER)

    assert student.last_pickup_on == four_weeks_ago.pickup_date


def test_a_fix_made_twice_says_so(db, monday, food, student, sam):
    """Two volunteers fixing the same bag: the second is told it's done."""
    bag = packed(db, monday, student, food, "quick oats")
    no_shows.mark_no_show(db, bag.id, NO_SHOW)
    no_shows.fix_to_picked_up(db, bag.id, sam, AFTER)

    problem = refused(db, CantFix, lambda: no_shows.fix_to_picked_up(db, bag.id, sam, AFTER))

    assert problem.message == f"Bag {bag.code} is picked up already."
    assert food["quick oats"].stock == 4


def test_a_cancelled_booking_has_nothing_to_fix(db, monday, food, student, sam):
    bag = booked(db, monday, student, food, "quick oats")
    booking_rules.cancel(db, student, OPEN)

    problem = refused(db, Problem, lambda: no_shows.fix_to_picked_up(db, bag.id, sam, AFTER))

    assert problem.message == f"Bag {bag.code} isn't a no-show or picked up, so there's nothing to fix."


# ---------- the last second at the counter, and the no-show job ----------

FAR_DAY = MONDAY + timedelta(days=1000)
FAR_NO_SHOW = datetime.combine(FAR_DAY, datetime.min.time(), tzinfo=UTC) + timedelta(hours=21, minutes=30)


@pytest.fixture
def world(engine):
    """Committed rows for the race test: a packed bag of oats on a far-off Monday. Deleted afterwards."""
    with Session(engine) as db:
        db.add(Settings(**SAMPLE_SETTINGS))
        staff = Staff(username="Race no-show", role="volunteer")
        category = Category(name="Race no-show shelf")
        day = PickupDay(
            pickup_date=FAR_DAY,
            booking_opens_at=FAR_NO_SHOW - timedelta(hours=25),
            booking_closes_at=FAR_NO_SHOW - timedelta(hours=6),
            pickup_starts_at=FAR_NO_SHOW - timedelta(hours=2, minutes=30),
            pickup_ends_at=FAR_NO_SHOW - timedelta(minutes=30),
            no_show_at=FAR_NO_SHOW,
        )
        db.add_all([staff, category, day])
        db.flush()
        item = Item(name="Race oats", category_id=category.id)
        slot = Slot(pickup_day_id=day.id, starts_at=FAR_NO_SHOW - timedelta(hours=2), capacity=1, booked_count=1)
        student = Student(id_hash=id_hash(ID_NUMBER), created_by_staff_id=staff.id)
        db.add_all([item, slot, student])
        db.flush()
        oats = Variety(item_id=item.id, name="Race quick oats", stock=4)
        db.add(oats)
        db.flush()
        bag = Booking(
            student_id=student.id,
            pickup_day_id=day.id,
            slot_id=slot.id,
            code="R4C",
            status="packed",
            packed_at=FAR_NO_SHOW - timedelta(hours=5),
            packed_by_staff_id=staff.id,
        )
        db.add(bag)
        db.flush()
        db.add(BookingItem(booking_id=bag.id, variety_id=oats.id))
        db.commit()
        ids = {
            "bag": bag.id,
            "oats": oats.id,
            "item": item.id,
            "category": category.id,
            "day": day.id,
            "student": student.id,
            "staff": staff.id,
        }
    yield ids
    with engine.begin() as tidy:
        tidy.execute(delete(AuditLog).where(AuditLog.staff_id == ids["staff"]))
        tidy.execute(delete(Booking).where(Booking.id == ids["bag"]))
        tidy.execute(delete(Slot).where(Slot.pickup_day_id == ids["day"]))
        tidy.execute(delete(PickupDay).where(PickupDay.id == ids["day"]))
        tidy.execute(delete(Variety).where(Variety.id == ids["oats"]))
        tidy.execute(delete(Item).where(Item.id == ids["item"]))
        tidy.execute(delete(Category).where(Category.id == ids["category"]))
        tidy.execute(delete(Student).where(Student.id == ids["student"]))
        tidy.execute(delete(Staff).where(Staff.id == ids["staff"]))
        tidy.execute(delete(Settings))


def test_hand_over_at_the_last_second_and_the_no_show_job_take_turns(engine, world):
    """A volunteer presses Hand over at 5:59 pm while the 6 pm job starts. The job
    waits for the student's lock, then finds the bag picked up and leaves it.
    Without the lock, it would mark a bag the student took as a no-show, and put
    its oats back on the shelf."""
    results = {}

    def run_job():
        with Session(engine) as db:
            results["job"] = no_shows.mark_no_show(db, world["bag"], FAR_NO_SHOW)
            db.commit()

    with Session(engine) as db:
        counter.hand_over(db, "R4C", ID_NUMBER, [], [], db.get(Staff, world["staff"]), FAR_NO_SHOW - timedelta(minutes=1))
        job = threading.Thread(target=run_job)
        job.start()
        wait_until_someone_is_waiting_for_a_lock(engine)
        db.commit()
    job.join(timeout=10)

    assert results == {"job": None}
    with Session(engine) as check:
        assert check.get(Booking, world["bag"]).status == "picked_up"
        assert check.get(Variety, world["oats"]).stock == 4


# ---------- food with no number (decided 12 Nov) ----------


def test_a_no_show_puts_nothing_back_on_food_with_no_number(db, monday, food, student, sam):
    """What-could-go-wrong problem 5: a count, then a no-show adding the same rice back.
    With no number there's nothing to add back, so it can't be counted twice."""
    food["rice"].stock = None
    bag = packed(db, monday, student, food, "quick oats", "rice")

    no_shows.mark_no_show(db, bag.id, NO_SHOW)
    assert (food["quick oats"].stock, food["rice"].stock) == (5, None)

    no_shows.fix_to_picked_up(db, bag.id, sam, AFTER)
    assert (food["quick oats"].stock, food["rice"].stock) == (4, None)
