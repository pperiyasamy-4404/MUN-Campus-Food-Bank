"""The counter addresses, used the way the counter pages use them.

The rules are tested in test_counter.py. These check the answers the pages
get, that only staff can use the counter, and that nothing about the student
comes back (P4).
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import Category, Item, Slot, Student, Variety
from app.security.keyed_hash import id_hash
from app.services import booking as booking_rules
from app.services import packing
from app.services.booking import Choice
from app.services.pickup_days import make_pickup_day
from tests.helpers import ID_NUMBER, MONDAY, OTHER_ID_NUMBER, add, log_in, make_staff, make_student, stop_the_clock_at

OPEN = datetime(2026, 11, 8, 21, 0, tzinfo=UTC)  # Sunday 5:30 pm
MORNING = datetime(2026, 11, 9, 13, 0, tzinfo=UTC)  # Monday 9:30 am
PACKING = datetime(2026, 11, 9, 16, 0, tzinfo=UTC)  # Monday 12:30 pm
COUNTER = datetime(2026, 11, 9, 19, 10, tzinfo=UTC)  # Monday 3:40 pm


@pytest.fixture
def setup(client, db_with_sample_week):
    """Monday, with a packed bag (quick oats) for the student whose card is ID_NUMBER,
    bread as an extra, and Sam logged in at the counter."""
    db = db_with_sample_week
    day = make_pickup_day(db, MONDAY)
    pantry = add(db, Category(name="Pantry"))
    oats = add(db, Item(name="Oats", category_id=pantry.id))
    bread = add(db, Item(name="Bread", category_id=pantry.id, is_extra=True))
    food = {
        "quick oats": add(db, Variety(item_id=oats.id, name="Quick oats", stock=5)),
        "white bread": add(db, Variety(item_id=bread.id, name="White bread", stock=3)),
    }
    student = add(db, Student(id_hash=id_hash(ID_NUMBER), created_by_staff_id=make_staff(db).id))
    first = db.scalars(select(Slot).where(Slot.pickup_day_id == day.id).order_by(Slot.starts_at)).first()
    booking_rules.hold_slot(db, student, first.id, OPEN)
    bag = booking_rules.book(db, student, [Choice(food["quick oats"].id)], [], OPEN)
    packing.pack(db, bag.id, [], [], [], make_staff(db, "Lee"), PACKING)
    log_in(client, db, make_staff(db, "Sam"), COUNTER)
    stop_the_clock_at(COUNTER)
    return {"bag": bag, "student": student, "food": food}


@pytest.mark.parametrize(
    "method, address",
    [
        ("GET", "/api/counter"),
        ("POST", "/api/counter/find"),
        ("POST", "/api/counter/pickups"),
        ("POST", "/api/walk-ins/check"),
        ("POST", "/api/walk-ins"),
    ],
)
def test_only_staff_use_the_counter(client, db_with_sample_week, method, address):
    db = db_with_sample_week
    stop_the_clock_at(COUNTER)
    assert client.request(method, address, json={}).status_code == 401
    log_in(client, db, make_student(db), COUNTER)
    assert client.request(method, address, json={}).status_code == 401


def test_the_counter_page_lists_the_shelf(client, setup):
    page = client.get("/api/counter").json()

    assert (page["pickup_date"], page["is_open"], page["why_not"]) == ("2026-11-09", True, None)
    assert (page["walk_ins_open"], page["walk_ins_why_not"]) == (True, None)
    assert page["limits"] == {"item_limit": 13, "max_per_item": 1}
    assert [line["variety"] for line in page["food"]] == ["Quick oats"]
    assert [(line["variety"], line["stock"]) for line in page["extras"]] == [("White bread", 3)]


def test_the_counter_page_says_when_it_opens(client, setup):
    stop_the_clock_at(MORNING)

    page = client.get("/api/counter").json()

    assert (page["is_open"], page["why_not"]) == (False, "The counter opens when booking closes, at 12:00 p.m.")
    assert (page["walk_ins_open"], page["walk_ins_why_not"]) == (False, page["why_not"])


def test_the_counter_page_says_when_walk_ins_are_served(client, setup):
    """Bags are handed over from 12 pm, walk-ins only during pickup hours (W3)."""
    stop_the_clock_at(PACKING)

    page = client.get("/api/counter").json()

    assert (page["is_open"], page["walk_ins_open"]) == (True, False)
    assert page["walk_ins_why_not"] == "Walk-ins are served from 3:30 p.m. to 5:30 p.m., during pickup hours."


def test_handing_over_a_bag_from_start_to_end(client, setup):
    code = setup["bag"].code

    found = client.post("/api/counter/find", json={"code": code.lower()}).json()
    assert (found["code"], found["status"], found["why_not"], found["short"]) == (code, "packed", None, 0)
    assert found["packed_by"] == "Lee"
    assert [(thing["variety"], thing["quantity"]) for thing in found["contents"]] == [("Quick oats", 1)]

    response = client.post(
        "/api/counter/pickups",
        json={"code": code, "id_number": ID_NUMBER, "extras": [setup["food"]["white bread"].id]},
    )
    assert response.status_code == 201
    assert response.json() == {"code": code, "picked_up_at": "2026-11-09T15:40:00-03:30", "next_pickup_on": "2026-12-07"}

    again = client.post("/api/counter/find", json={"code": code}).json()
    assert (again["status"], again["picked_up_by"]) == ("picked_up", "Sam")
    assert again["given_at_counter"] == [{"variety": "White bread", "item": "Bread", "quantity": 1, "is_extra": True}]
    assert again["why_not"] == f"Bag {code} was picked up already, at 3:40 p.m."


def test_a_card_that_does_not_match_is_refused(client, setup):
    response = client.post("/api/counter/pickups", json={"code": setup["bag"].code, "id_number": OTHER_ID_NUMBER})

    assert response.status_code == 400
    assert response.json()["detail"].startswith("That card doesn't match bag")
    assert OTHER_ID_NUMBER not in response.text


def test_a_mistyped_card_number_answers_422(client, setup):
    response = client.post("/api/walk-ins/check", json={"id_number": "12345"})

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {"loc": ["body", "id_number"], "msg": "Enter the 9 digits on your MUN card.", "type": "id_number"}
    ]


def test_a_walk_in_from_start_to_end(client, setup):
    checked = client.post("/api/walk-ins/check", json={"id_number": OTHER_ID_NUMBER}).json()
    assert checked == {"can_serve": True, "why_not": None, "new_account": True, "cancels": None}

    response = client.post(
        "/api/walk-ins",
        json={
            "id_number": OTHER_ID_NUMBER,
            "food": [{"variety_id": setup["food"]["quick oats"].id}],
            "extras": [setup["food"]["white bread"].id],
        },
    )

    assert response.status_code == 201
    done = response.json()
    assert (done["things"], done["extras"], done["new_account"], done["cancelled"]) == (1, 1, True, None)
    assert done["next_pickup_on"] == "2026-12-07"
    again = client.post("/api/walk-ins/check", json={"id_number": OTHER_ID_NUMBER}).json()
    assert (again["can_serve"], again["why_not"]) == (False, "Not yet. Their next pickup can be on Monday, December 7 or later.")


def test_a_student_with_a_bag_today_is_sent_to_their_bag(client, setup):
    checked = client.post("/api/walk-ins/check", json={"id_number": ID_NUMBER}).json()

    assert checked["can_serve"] is False
    assert checked["why_not"] == f"They booked for today: bag {setup['bag'].code}, at 3:30 p.m. Hand over that bag instead."


def test_counter_answers_show_nothing_about_the_student(client, setup):
    """P4: the code and the food, never the hash or the account."""
    answers = [
        client.get("/api/counter").text,
        client.post("/api/counter/find", json={"code": setup["bag"].code}).text,
        client.post("/api/walk-ins/check", json={"id_number": ID_NUMBER}).text,
        client.post("/api/counter/pickups", json={"code": setup["bag"].code, "id_number": ID_NUMBER}).text,
    ]

    for answer in answers:
        assert setup["student"].id_hash not in answer
        assert "student" not in answer
