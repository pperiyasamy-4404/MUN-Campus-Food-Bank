"""The fix page's addresses, used the way the page uses them (B6).

The rules are tested in test_no_shows.py. These check the answers the page
gets, that only staff can fix, and that nothing about the student comes back (P4).
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import Category, Item, Slot, Student, Variety
from app.security.keyed_hash import id_hash
from app.services import booking as booking_rules
from app.services import counter, no_shows, packing
from app.services.booking import Choice
from app.services.pickup_days import make_pickup_day
from tests.helpers import ID_NUMBER, MONDAY, OTHER_ID_NUMBER, THURSDAY, add, log_in, make_staff, make_student, stop_the_clock_at

OPEN = datetime(2026, 11, 8, 21, 0, tzinfo=UTC)  # Sunday 5:30 pm
PACKING = datetime(2026, 11, 9, 16, 0, tzinfo=UTC)  # Monday 12:30 pm
COUNTER = datetime(2026, 11, 9, 19, 10, tzinfo=UTC)  # Monday 3:40 pm
NO_SHOW = datetime(2026, 11, 9, 21, 30, tzinfo=UTC)  # Monday 6:00 pm
AFTER = datetime(2026, 11, 9, 21, 45, tzinfo=UTC)  # Monday 6:15 pm


@pytest.fixture
def setup(client, db_with_sample_week):
    """Monday is over. One bag was handed over by Sam, the other is a no-show.
    Thursday is made too, so booking for it opens on Wednesday at 5 pm. Lee is logged in."""
    db = db_with_sample_week
    monday = make_pickup_day(db, MONDAY)
    make_pickup_day(db, THURSDAY)
    pantry = add(db, Category(name="Pantry"))
    oats = add(db, Variety(item_id=add(db, Item(name="Oats", category_id=pantry.id)).id, name="Quick oats", stock=5))
    sam = make_staff(db, "Sam")
    bags = []
    for card in [ID_NUMBER, OTHER_ID_NUMBER]:
        student = add(db, Student(id_hash=id_hash(card), created_by_staff_id=sam.id))
        free = db.scalars(
            select(Slot).where(Slot.pickup_day_id == monday.id, Slot.booked_count == 0).order_by(Slot.starts_at)
        ).first()
        booking_rules.hold_slot(db, student, free.id, OPEN)
        bag = booking_rules.book(db, student, [Choice(oats.id)], [], OPEN)
        packing.pack(db, bag.id, [], [], [], sam, PACKING)
        bags.append(bag)
    handed_over, no_show = bags
    counter.hand_over(db, handed_over.code, ID_NUMBER, [], [], sam, COUNTER)
    no_shows.mark_no_show(db, no_show.id, NO_SHOW)
    log_in(client, db, make_staff(db, "Lee"), AFTER)
    stop_the_clock_at(AFTER)
    return {"handed_over": handed_over, "no_show": no_show, "oats": oats}


@pytest.mark.parametrize(
    "method, address",
    [("GET", "/api/fixes"), ("POST", "/api/fixes/1/picked-up"), ("POST", "/api/fixes/1/no-show")],
)
def test_only_staff_fix_pickups(client, db_with_sample_week, method, address):
    db = db_with_sample_week
    stop_the_clock_at(AFTER)
    assert client.request(method, address).status_code == 401
    log_in(client, db, make_student(db), AFTER)
    assert client.request(method, address).status_code == 401


def test_the_fix_page_lists_the_days_bags(client, setup):
    page = client.get("/api/fixes").json()

    assert (page["days"], page["day"]) == (["2026-11-09"], "2026-11-09")
    # Fix before booking opens for Thursday: Wednesday at 5 pm.
    assert page["fix_before"] == "2026-11-11T17:00:00-03:30"
    bags = {bag["code"]: bag for bag in page["bags"]}
    handed_over = bags[setup["handed_over"].code]
    assert (handed_over["status"], handed_over["picked_up_by"], handed_over["why_not"]) == ("picked_up", "Sam", None)
    assert bags[setup["no_show"].code]["status"] == "no_show"


def test_the_fix_page_waits_until_the_day_is_over(client, setup):
    stop_the_clock_at(COUNTER)

    assert client.get("/api/fixes").json() == {"days": [], "day": None, "fix_before": None, "bags": []}


def test_fixing_both_ways(client, setup):
    no_show, handed_over = setup["no_show"], setup["handed_over"]

    fixed = client.post(f"/api/fixes/{no_show.id}/picked-up").json()
    assert (fixed["code"], fixed["status"], fixed["picked_up_by"]) == (no_show.code, "picked_up", "Lee")

    fixed = client.post(f"/api/fixes/{handed_over.id}/no-show").json()
    assert (fixed["code"], fixed["status"], fixed["picked_up_by"]) == (handed_over.code, "no_show", None)


def test_a_fix_made_twice_is_refused(client, setup):
    bag = setup["no_show"]
    client.post(f"/api/fixes/{bag.id}/picked-up")

    response = client.post(f"/api/fixes/{bag.id}/picked-up")

    assert response.status_code == 409
    assert response.json()["detail"] == f"Bag {bag.code} is picked up already."


def test_another_day_that_has_nothing_to_fix(client, setup):
    response = client.get("/api/fixes", params={"day": "2026-11-12"})

    assert response.status_code == 404


def test_nothing_about_the_student_comes_back(client, setup):
    """P4: the bag's code only, never the hash of the card."""
    answers = [
        client.get("/api/fixes").text,
        client.post(f"/api/fixes/{setup['no_show'].id}/picked-up").text,
    ]
    for answer in answers:
        assert id_hash(ID_NUMBER) not in answer
        assert id_hash(OTHER_ID_NUMBER) not in answer
        assert "student" not in answer
