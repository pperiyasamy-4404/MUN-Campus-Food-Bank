"""The counter, checked straight from app/services/counter.py.

Handing over a booked bag (P5, B2, B3, U6, E3), walk-ins (W1, W4), and two
"at the same moment" tests. The web side is in test_counter_api.py.

The pickup day is Monday 9 November 2026. With the sample settings booking
closes at 12 pm, pickup is 3:30 to 5:30 pm and no-shows are at 6 pm, St. John's
time (UTC-3:30 in November).
"""

import threading
from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Booking,
    BookingItem,
    Category,
    CounterItem,
    Hold,
    Item,
    PickupDay,
    PickupHours,
    Settings,
    Slot,
    Staff,
    Student,
    Variety,
    WalkIn,
)
from app.problems import NotFound, Problem
from app.sample_data import SAMPLE_SETTINGS
from app.security.keyed_hash import id_hash
from app.services import booking as booking_rules
from app.services import counter, packing
from app.services.booking import Choice, TimeTaken
from app.services.counter import AlreadyPickedUp, BookingToCancel, NotPackedYet
from app.services.packing import Missing
from app.services.pickup_days import make_pickup_day
from tests.helpers import (
    ID_NUMBER,
    MONDAY,
    OTHER_ID_NUMBER,
    THURSDAY,
    add,
    make_staff,
    wait_until_someone_is_waiting_for_a_lock,
)

OPEN = datetime(2026, 11, 8, 21, 0, tzinfo=UTC)  # Sunday 5:30 pm: booking for Monday is open
MORNING = datetime(2026, 11, 9, 13, 0, tzinfo=UTC)  # Monday 9:30 am
PACKING = datetime(2026, 11, 9, 16, 0, tzinfo=UTC)  # Monday 12:30 pm
PICKUP_STARTS = datetime(2026, 11, 9, 19, 0, tzinfo=UTC)  # Monday 3:30 pm
COUNTER = datetime(2026, 11, 9, 19, 10, tzinfo=UTC)  # Monday 3:40 pm
PICKUP_ENDS = datetime(2026, 11, 9, 21, 0, tzinfo=UTC)  # Monday 5:30 pm
LATE = datetime(2026, 11, 9, 21, 15, tzinfo=UTC)  # Monday 5:45 pm
NO_SHOW = datetime(2026, 11, 9, 21, 30, tzinfo=UTC)  # Monday 6:00 pm
A_MOMENT = timedelta(microseconds=1)
TUESDAY = datetime(2026, 11, 10, 16, 0, tzinfo=UTC)  # not a pickup day


# ---------- the world ----------


@pytest.fixture
def monday(db_with_sample_week) -> PickupDay:
    return make_pickup_day(db_with_sample_week, MONDAY)


@pytest.fixture
def food(db_with_sample_week) -> dict[str, Variety]:
    """Food from the examples, 5 of each, and two extras: bread (two kinds) and eggs."""
    db = db_with_sample_week
    pantry = add(db, Category(name="Pantry"))
    items: dict[str, Item] = {}

    def variety(item_name: str, name: str, is_extra: bool = False) -> Variety:
        if item_name not in items:
            items[item_name] = add(db, Item(name=item_name, category_id=pantry.id, is_extra=is_extra))
        return add(db, Variety(item_id=items[item_name].id, name=name, stock=5))

    return {
        "quick oats": variety("Oats", "Quick oats"),
        "steel-cut oats": variety("Oats", "Steel-cut oats"),
        "sunflower oil": variety("Cooking oil", "Sunflower oil"),
        "black beans": variety("Beans", "Black beans"),
        "rice": variety("Rice", "White rice"),
        "lentils": variety("Lentils", "Red lentils"),
        "white bread": variety("Bread", "White bread", is_extra=True),
        "brown bread": variety("Bread", "Whole wheat bread", is_extra=True),
        "eggs": variety("Eggs", "Dozen eggs", is_extra=True),
    }


@pytest.fixture
def sam(db_with_sample_week) -> Staff:
    return make_staff(db_with_sample_week, "Sam")


def card_holder(db, card: str = ID_NUMBER) -> Student:
    """The student whose MUN card has this number."""
    return add(db, Student(id_hash=id_hash(card), created_by_staff_id=make_staff(db).id))


def booked(db, day: PickupDay, student: Student, food, *names: str, substitutes=(), at: datetime = OPEN) -> Booking:
    """The student books these, in the day's next free time."""
    free = db.scalars(
        select(Slot).where(Slot.pickup_day_id == day.id, Slot.booked_count == 0).order_by(Slot.starts_at)
    ).first()
    booking_rules.hold_slot(db, student, free.id, at)
    return booking_rules.book(db, student, [Choice(food[n].id) for n in names], [food[n].id for n in substitutes], at)


def packed(db, monday, student, food, *names: str, missing=(), substitutes=(), uses=()) -> Booking:
    """Booked on Sunday, packed on Monday at 12:30."""
    bag = booked(db, monday, student, food, *names, substitutes=substitutes)
    packing.pack(
        db,
        bag.id,
        [Missing(food[n].id) for n in missing],
        [],
        [food[n].id for n in uses],
        make_staff(db),
        PACKING,
    )
    return bag


def refused(db, kind, call):
    """Expect a refusal, and undo whatever the call did, the way the route's missing commit would."""
    with pytest.raises(kind) as refusal:
        with db.begin_nested():
            call()
    return refusal.value


# ---------- when the counter is open ----------


@pytest.mark.parametrize(
    "now, message",
    [
        (MORNING, "The counter opens when booking closes, at 12:00 p.m."),
        (NO_SHOW, "Pickup for Monday, November 9 is over."),
        (TUESDAY, "Today isn't a pickup day. The next one is Thursday, November 12."),
    ],
)
def test_the_counter_is_open_from_booking_close_until_the_no_show_time(db, monday, now, message):
    make_pickup_day(db, THURSDAY)

    problem = refused(db, Problem, lambda: counter.find_bag(db, "K3P", now))

    assert problem.message == message


def test_a_closed_day_has_no_counter(db, monday):
    monday.closed_at, monday.closed_reason = PACKING, "Snow day"

    problem = refused(db, Problem, lambda: counter.check_walk_in(db, ID_NUMBER, COUNTER))

    assert problem.message == "Monday, November 9 is closed: Snow day"


@pytest.mark.parametrize(
    "now, message",
    [
        (PACKING, "Walk-ins are served from 3:30 p.m. to 5:30 p.m., during pickup hours."),
        (LATE, "Walk-ins are over for today. They're served from 3:30 p.m. to 5:30 p.m., during pickup hours."),
        (NO_SHOW, "Pickup for Monday, November 9 is over."),
    ],
)
def test_walk_ins_are_served_only_during_pickup_hours(db, monday, food, sam, now, message):
    checked = refused(db, Problem, lambda: counter.check_walk_in(db, ID_NUMBER, now))
    recorded = refused(
        db, Problem, lambda: counter.record_walk_in(db, ID_NUMBER, [Choice(food["rice"].id)], [], False, sam, now)
    )

    assert checked.message == recorded.message == message
    assert db.scalar(select(func.count()).select_from(WalkIn)) == 0


@pytest.mark.parametrize(
    "now, served",
    [(PICKUP_STARTS - A_MOMENT, False), (PICKUP_STARTS, True), (PICKUP_ENDS - A_MOMENT, True), (PICKUP_ENDS, False)],
)
def test_walk_ins_start_the_moment_pickup_starts_and_stop_the_moment_it_ends(db, monday, now, served):
    assert (counter.why_walk_ins_closed(db, monday, now) is None) == served


def test_walk_in_hours_are_the_days_own(db, monday, food, sam):
    """Changing the weekly pickup hours doesn't move a day that's already made."""
    db.get(PickupHours, 1).starts_at = time(15, 0)
    db.flush()

    problem = refused(db, Problem, lambda: counter.check_walk_in(db, ID_NUMBER, PICKUP_STARTS - timedelta(minutes=15)))

    assert problem.message == "Walk-ins are served from 3:30 p.m. to 5:30 p.m., during pickup hours."


def test_a_late_student_still_gets_their_bag_after_walk_ins_end(db, monday, food, sam):
    """Only walk-ins stop at 5:30. A booked bag waits for its student until the no-show time."""
    bag = packed(db, monday, card_holder(db), food, "quick oats")

    counter.hand_over(db, bag.code, ID_NUMBER, [], [], sam, LATE)

    assert bag.status == "picked_up"


# ---------- handing over a booked bag (P5, B2, B3) ----------


def test_handing_over_a_packed_bag(db, monday, food, sam):
    student = card_holder(db)
    bag = packed(db, monday, student, food, "quick oats", "rice")

    counter.hand_over(db, bag.code.lower(), ID_NUMBER, [], [], sam, COUNTER)

    assert (bag.status, bag.picked_up_at, bag.picked_up_by_staff_id) == ("picked_up", COUNTER, sam.id)
    # F1: the next pickup is 30 calendar days after today.
    assert student.last_pickup_on == MONDAY
    assert booking_rules.next_pickup_allowed_on(db, student, db.get(Settings, 1)) == MONDAY + timedelta(days=30)
    logged = db.scalar(select(AuditLog).where(AuditLog.booking_id == bag.id))
    assert (logged.action, logged.staff_id, logged.student_id) == ("marked_picked_up", sam.id, student.id)


def test_the_card_must_match_the_booking(db, monday, food, sam):
    """P5: booking online proves nothing. The card at the counter does."""
    bag = packed(db, monday, card_holder(db), food, "quick oats")

    problem = refused(db, Problem, lambda: counter.hand_over(db, bag.code, OTHER_ID_NUMBER, [], [], sam, COUNTER))

    assert problem.message == (
        f"That card doesn't match bag {bag.code}. Check the code and the card. Don't hand over the bag until they match."
    )
    db.expire_all()
    assert db.get(Booking, bag.id).status == "packed"


def test_only_a_packed_bag_is_handed_over(db, monday, food, sam):
    """B2: booked -> packed -> picked up. A bag still to pack goes to the Packing page first."""
    bag = booked(db, monday, card_holder(db), food, "quick oats")

    problem = refused(db, NotPackedYet, lambda: counter.hand_over(db, bag.code, ID_NUMBER, [], [], sam, COUNTER))

    assert problem.message == f"Bag {bag.code} isn't packed yet. Pack it on the Packing page, then hand it over."


def test_a_bag_is_handed_over_once(db, monday, food, sam):
    bag = packed(db, monday, card_holder(db), food, "quick oats")
    counter.hand_over(db, bag.code, ID_NUMBER, [], [], sam, COUNTER)

    problem = refused(db, AlreadyPickedUp, lambda: counter.hand_over(db, bag.code, ID_NUMBER, [], [], sam, COUNTER))

    assert problem.message == f"Bag {bag.code} was picked up already, at 3:40 p.m."


def test_a_code_from_another_day_is_not_found(db, monday, food, sam):
    thursday = make_pickup_day(db, THURSDAY)
    thursday.booking_opens_at = OPEN
    bag = booked(db, thursday, card_holder(db), food, "quick oats")

    problem = refused(db, NotFound, lambda: counter.find_bag(db, bag.code, COUNTER))

    assert problem.message == f"There's no bag {bag.code} today. Check the code with the student."


# ---------- a short bag, and extras (U6, E3) ----------


def test_a_short_bag_is_filled_from_the_shelf(db, monday, food, sam):
    """The black beans weren't on the shelf and there were no substitutes: the student chooses lentils."""
    bag = packed(db, monday, card_holder(db), food, "quick oats", "black beans", missing=["black beans"])

    counter.hand_over(db, bag.code, ID_NUMBER, [Choice(food["lentils"].id)], [], sam, COUNTER)

    assert food["lentils"].stock == 4
    row = db.scalar(select(CounterItem).where(CounterItem.booking_id == bag.id))
    assert (row.variety_id, row.is_extra, row.quantity) == (food["lentils"].id, False, 1)


@pytest.mark.parametrize(
    "choices, message",
    [
        (["lentils", "rice"], "The bag is 1 short, so they can choose 1 thing from the shelf."),
        (["steel-cut oats"], "Oats: 1 at most, counting all its kinds together."),
        (["white bread"], "Bread is an extra: add it under Extras."),
    ],
)
def test_a_gap_is_filled_within_the_same_limits(db, monday, food, sam, choices, message):
    bag = packed(db, monday, card_holder(db), food, "quick oats", "black beans", missing=["black beans"])

    problem = refused(
        db, Problem, lambda: counter.hand_over(db, bag.code, ID_NUMBER, [Choice(food[n].id) for n in choices], [], sam, COUNTER)
    )

    assert problem.message == message


def test_a_full_bag_has_nothing_to_choose(db, monday, food, sam):
    bag = packed(db, monday, card_holder(db), food, "quick oats")

    problem = refused(
        db, Problem, lambda: counter.hand_over(db, bag.code, ID_NUMBER, [Choice(food["rice"].id)], [], sam, COUNTER)
    )

    assert problem.message == "The bag isn't short, so there's nothing to choose from the shelf. Extras go under Extras."


def test_extras_are_one_of_each(db, monday, food, sam):
    """E3: one bread, even with two kinds of bread. Eggs as well is fine."""
    bag = packed(db, monday, card_holder(db), food, "quick oats")
    two_breads = [food["white bread"].id, food["brown bread"].id]

    problem = refused(db, Problem, lambda: counter.hand_over(db, bag.code, ID_NUMBER, [], two_breads, sam, COUNTER))
    counter.hand_over(db, bag.code, ID_NUMBER, [], [food["white bread"].id, food["eggs"].id], sam, COUNTER)

    assert problem.message == "One Bread only: extras are one of each."
    assert (food["white bread"].stock, food["eggs"].stock, food["brown bread"].stock) == (4, 4, 5)
    assert db.scalar(select(func.count()).select_from(CounterItem).where(CounterItem.is_extra)) == 2


@pytest.mark.parametrize(
    "extra, stock, kind, message",
    [
        ("quick oats", 5, Problem, "Quick oats isn't an extra."),
        ("eggs", 0, TimeTaken, "There's no Dozen eggs left. Choose something else."),
    ],
)
def test_an_extra_must_be_an_extra_and_on_the_shelf(db, monday, food, sam, extra, stock, kind, message):
    bag = packed(db, monday, card_holder(db), food, "rice")
    food[extra].stock = stock

    problem = refused(db, kind, lambda: counter.hand_over(db, bag.code, ID_NUMBER, [], [food[extra].id], sam, COUNTER))

    assert problem.message == message


# ---------- walk-ins (W1, W4) ----------


def test_a_first_visit_walk_in_gets_an_account(db, monday, food, sam):
    """A new student can take food as a walk-in on their first visit (CONSTRAINTS.md, known issues)."""
    checked = counter.check_walk_in(db, ID_NUMBER, COUNTER)

    recorded = counter.record_walk_in(
        db, ID_NUMBER, [Choice(food["rice"].id), Choice(food["lentils"].id)], [food["eggs"].id], False, sam, COUNTER
    )

    assert (checked.can_serve, checked.new_account) == (True, True)
    assert recorded.new_account is True
    student = db.scalar(select(Student).where(Student.id_hash == id_hash(ID_NUMBER)))
    assert student.last_pickup_on == MONDAY
    assert recorded.next_pickup_on == date(2026, 12, 9)
    assert (food["rice"].stock, food["lentils"].stock, food["eggs"].stock) == (4, 4, 4)
    assert db.scalar(select(func.count()).select_from(CounterItem).where(CounterItem.walk_in_id == recorded.walk_in.id)) == 3
    actions = db.scalars(select(AuditLog.action).where(AuditLog.student_id == student.id).order_by(AuditLog.id)).all()
    assert actions == ["created_student", "recorded_walk_in"]


def test_a_walk_in_within_30_days_is_refused(db, monday, food, sam):
    """No exception (decided 7 Nov): one pickup every 30 days, however they come."""
    student = card_holder(db)
    student.last_pickup_on = MONDAY - timedelta(days=10)

    checked = counter.check_walk_in(db, ID_NUMBER, COUNTER)
    problem = refused(
        db, Problem, lambda: counter.record_walk_in(db, ID_NUMBER, [Choice(food["rice"].id)], [], False, sam, COUNTER)
    )

    assert (checked.can_serve, checked.why_not) == (False, "Not yet. Their next pickup can be on Sunday, November 29 or later.")
    assert problem.message == checked.why_not


def test_a_second_walk_in_the_same_day_is_refused(db, monday, food, sam):
    counter.record_walk_in(db, ID_NUMBER, [Choice(food["rice"].id)], [], False, sam, COUNTER)

    checked = counter.check_walk_in(db, ID_NUMBER, COUNTER)

    assert checked.why_not == "Not yet. Their next pickup can be on Wednesday, December 9 or later."


def test_a_walk_in_who_booked_today_gets_their_bag_instead(db, monday, food, sam):
    bag = booked(db, monday, card_holder(db), food, "quick oats")

    checked = counter.check_walk_in(db, ID_NUMBER, COUNTER)

    assert checked.why_not == f"They booked for today: bag {bag.code}, at 3:30 p.m. Hand over that bag instead."


def test_a_walk_in_with_a_later_booking_cancels_it_if_the_volunteer_says_so(db, monday, food, sam):
    """W4. Booking for Thursday opened early here, so the booking exists on Monday."""
    thursday = make_pickup_day(db, THURSDAY)
    thursday.booking_opens_at = OPEN
    student = card_holder(db)
    later = booked(db, thursday, student, food, "quick oats")
    slot = db.get(Slot, later.slot_id)
    assert (food["quick oats"].stock, slot.booked_count) == (4, 1)

    checked = counter.check_walk_in(db, ID_NUMBER, COUNTER)
    asked = refused(
        db, BookingToCancel, lambda: counter.record_walk_in(db, ID_NUMBER, [Choice(food["rice"].id)], [], False, sam, COUNTER)
    )
    recorded = counter.record_walk_in(db, ID_NUMBER, [Choice(food["rice"].id)], [], True, sam, COUNTER)

    assert (checked.can_serve, checked.cancels, checked.cancels_on) == (True, later, THURSDAY)
    assert asked.message == f"They have a booking for Thursday, November 12 (bag {later.code}). Serving them now cancels it."
    assert recorded.cancelled == later
    assert (later.status, later.cancel_reason) == ("cancelled", "walk_in")
    # Its place and its food went back for someone else.
    assert (slot.booked_count, food["quick oats"].stock, food["rice"].stock) == (0, 5, 4)


@pytest.mark.parametrize(
    "food_names, message",
    [
        ([], "Choose what they took."),
        (["quick oats", "steel-cut oats"], "Oats: 1 at most, counting all its kinds together."),
        (["quick oats", "rice", "lentils"], "A walk-in can take up to 2 things."),
    ],
)
def test_a_walk_in_takes_food_within_the_same_limits(db, monday, food, sam, food_names, message):
    db.get(Settings, 1).item_limit = 2

    problem = refused(
        db,
        Problem,
        lambda: counter.record_walk_in(db, ID_NUMBER, [Choice(food[n].id) for n in food_names], [], False, sam, COUNTER),
    )

    assert problem.message == message


def test_a_walk_in_only_takes_what_nobody_booked(db, monday, food, sam):
    """The last rice on the shelf is in a booked bag, so stock says none (I4)."""
    food["rice"].stock = 0

    problem = refused(
        db, TimeTaken, lambda: counter.record_walk_in(db, ID_NUMBER, [Choice(food["rice"].id)], [], False, sam, COUNTER)
    )

    assert problem.message == "There's no White rice left. Choose something else."
    assert db.scalar(select(func.count()).select_from(WalkIn)) == 0


def test_after_a_walk_in_booking_online_waits_30_days(db, monday, food, sam):
    """W1: nobody can walk in one week and book online the next."""
    thursday = make_pickup_day(db, THURSDAY)
    thursday.booking_opens_at = OPEN
    counter.record_walk_in(db, ID_NUMBER, [Choice(food["rice"].id)], [], False, sam, COUNTER)
    student = db.scalar(select(Student).where(Student.id_hash == id_hash(ID_NUMBER)))
    first_slot = db.scalars(select(Slot).where(Slot.pickup_day_id == thursday.id)).first()

    problem = refused(db, Problem, lambda: booking_rules.hold_slot(db, student, first_slot.id, COUNTER))

    assert problem.message == "Your next pickup can be on Wednesday, December 9 or later."


# ---------- at the same moment ----------

FAR_DAY = MONDAY + timedelta(days=910)
FAR_NOW = datetime.combine(FAR_DAY, datetime.min.time(), tzinfo=UTC) + timedelta(hours=19)


@pytest.fixture
def world(engine):
    """Committed rows for the race tests. Today is a pickup day with the counter open,
    and a later day is open for booking. Two students with cards, one tin left, and plenty of another food."""
    with Session(engine) as db:
        db.add(Settings(**SAMPLE_SETTINGS))
        staff = Staff(username="Race counter", role="volunteer")
        category = Category(name="Race shelf")
        today = PickupDay(
            pickup_date=FAR_DAY,
            booking_opens_at=FAR_NOW - timedelta(hours=26),
            booking_closes_at=FAR_NOW - timedelta(hours=3),
            pickup_starts_at=FAR_NOW - timedelta(hours=1),
            pickup_ends_at=FAR_NOW + timedelta(hours=1),
            no_show_at=FAR_NOW + timedelta(hours=2),
        )
        later = PickupDay(
            pickup_date=FAR_DAY + timedelta(days=3),
            booking_opens_at=FAR_NOW - timedelta(hours=1),
            booking_closes_at=FAR_NOW + timedelta(days=3),
            pickup_starts_at=FAR_NOW + timedelta(days=3, hours=3),
            pickup_ends_at=FAR_NOW + timedelta(days=3, hours=5),
            no_show_at=FAR_NOW + timedelta(days=3, hours=6),
        )
        db.add_all([staff, category, today, later])
        db.flush()
        item = Item(name="Race tin", category_id=category.id)
        slot = Slot(pickup_day_id=later.id, starts_at=FAR_NOW + timedelta(days=3, hours=4), capacity=1)
        students = [Student(id_hash=id_hash(card), created_by_staff_id=staff.id) for card in (ID_NUMBER, OTHER_ID_NUMBER)]
        db.add_all([item, slot, *students])
        db.flush()
        tin = Variety(item_id=item.id, name="Last tin", stock=1)
        # Plenty of something else, so a race over it can only be about the pickup gap.
        plenty = Variety(item_id=item.id, name="Plenty", stock=50)
        db.add_all([tin, plenty])
        db.commit()
        ids = {
            "staff": staff.id,
            "category": category.id,
            "days": [today.id, later.id],
            "item": item.id,
            "slot": slot.id,
            "students": [student.id for student in students],
            "tin": tin.id,
            "plenty": plenty.id,
        }
    yield ids
    with engine.begin() as tidy:
        tidy.execute(delete(WalkIn).where(WalkIn.pickup_day_id.in_(ids["days"])))
        tidy.execute(delete(Booking).where(Booking.pickup_day_id.in_(ids["days"])))
        tidy.execute(delete(Hold).where(Hold.student_id.in_(ids["students"])))
        tidy.execute(delete(Slot).where(Slot.id == ids["slot"]))
        tidy.execute(delete(PickupDay).where(PickupDay.id.in_(ids["days"])))
        tidy.execute(delete(Variety).where(Variety.id.in_([ids["tin"], ids["plenty"]])))
        tidy.execute(delete(Item).where(Item.id == ids["item"]))
        tidy.execute(delete(Category).where(Category.id == ids["category"]))
        tidy.execute(delete(AuditLog).where(AuditLog.student_id.in_(ids["students"])))
        tidy.execute(delete(Student).where(Student.id.in_(ids["students"])))
        tidy.execute(delete(Staff).where(Staff.id == ids["staff"]))
        tidy.execute(delete(Settings))


def at_the_same_moment(engine, first, second) -> dict:
    """Run first() and, while its transaction is still open, second() on another connection."""
    results = {}

    def run_second():
        with Session(engine) as db:
            try:
                second(db)
                db.commit()
                results["second"] = "done"
            except Problem as refusal:
                results["second"] = refusal

    with Session(engine) as db:
        first(db)
        racer = threading.Thread(target=run_second)
        racer.start()
        wait_until_someone_is_waiting_for_a_lock(engine)
        db.commit()
    racer.join(timeout=10)
    return results


def test_a_walk_in_and_an_online_booking_at_the_same_moment(engine, world):
    """The student is at the counter while their phone presses Book for a later day.
    Book waits for the walk-in, then sees the pickup gap (F1, W1). They choose
    different food, so only the student's lock makes Book wait."""
    with Session(engine) as db:
        booking_rules.hold_slot(db, db.get(Student, world["students"][0]), world["slot"], FAR_NOW)
        db.commit()

    def walk_in(db):
        staff = db.get(Staff, world["staff"])
        counter.record_walk_in(db, ID_NUMBER, [Choice(world["tin"])], [], False, staff, FAR_NOW)

    def book(db):
        booking_rules.book(db, db.get(Student, world["students"][0]), [Choice(world["plenty"])], [], FAR_NOW)

    results = at_the_same_moment(engine, walk_in, book)

    assert isinstance(results["second"], Problem)
    assert results["second"].message.startswith("Your next pickup can be on")
    with Session(engine) as check:
        assert check.scalar(select(func.count()).select_from(Booking).where(Booking.pickup_day_id.in_(world["days"]))) == 0


def test_two_walk_ins_take_the_last_tin_at_the_same_moment(engine, world):
    """Two volunteers, two students, one tin (I4). The second is told it's gone."""

    def walk_in(card):
        def run(db):
            counter.record_walk_in(db, card, [Choice(world["tin"])], [], False, db.get(Staff, world["staff"]), FAR_NOW)

        return run

    results = at_the_same_moment(engine, walk_in(ID_NUMBER), walk_in(OTHER_ID_NUMBER))

    assert isinstance(results["second"], TimeTaken)
    with Session(engine) as check:
        assert check.get(Variety, world["tin"]).stock == 0
        assert check.scalar(select(func.count()).select_from(WalkIn).where(WalkIn.pickup_day_id == world["days"][0])) == 1


# ---------- food with no number (decided 12 Nov) ----------


def test_food_with_no_number_is_on_the_counter_shelf_and_keeps_no_number(db, monday, food, sam):
    food["rice"].stock = None
    food["eggs"].stock = None

    on_shelf = {line.variety.name for line in counter.on_the_shelf(db)}
    counter.record_walk_in(db, ID_NUMBER, [Choice(food["rice"].id)], [food["eggs"].id], False, sam, COUNTER)

    assert {"White rice", "Dozen eggs"} <= on_shelf
    assert (food["rice"].stock, food["eggs"].stock) == (None, None)
