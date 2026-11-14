"""The packing addresses, used the way the packing pages use them.

The rules are tested in test_packing.py. These check the answers the pages get,
that only staff can pack, and that a bag shows nothing about the student (P4).
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Category, Item, Slot, Student, Variety
from app.services import booking as booking_rules
from app.services.booking import Choice
from app.services.pickup_days import make_pickup_day
from tests.helpers import MONDAY, add, log_in, make_staff, make_student, stop_the_clock_at

OPEN = datetime(2026, 11, 8, 21, 0, tzinfo=UTC)  # Sunday 5:30 pm
MORNING = datetime(2026, 11, 9, 13, 0, tzinfo=UTC)  # Monday 9:30 am
PACKING = datetime(2026, 11, 9, 16, 0, tzinfo=UTC)  # Monday 12:30 pm


@pytest.fixture
def setup(client, db_with_sample_week):
    """Monday's pickup day, a student's bag with sunflower oil in it and rice as a
    substitute, and a volunteer called Sam logged in on the test's browser."""
    db = db_with_sample_week
    day = make_pickup_day(db, MONDAY)
    pantry = add(db, Category(name="Pantry"))
    oil = add(db, Item(name="Cooking oil", category_id=pantry.id))
    rice = add(db, Item(name="Rice", category_id=pantry.id))
    food = {
        "sunflower oil": add(db, Variety(item_id=oil.id, name="Sunflower oil", stock=5)),
        "rice": add(db, Variety(item_id=rice.id, name="White rice", stock=5)),
    }
    student = make_student(db)
    first = db.scalars(select(Slot).where(Slot.pickup_day_id == day.id).order_by(Slot.starts_at)).first()
    booking_rules.hold_slot(db, student, first.id, OPEN)
    bag = booking_rules.book(db, student, [Choice(food["sunflower oil"].id)], [food["rice"].id], OPEN)
    # Logged in at packing time: a staff login lasts 12 hours, so Sunday's would have run out.
    log_in(client, db, make_staff(db, "Sam"), MORNING)
    stop_the_clock_at(PACKING)
    return {"bag": bag, "student": student, "food": food}


def oil_missing(setup) -> dict:
    return {"missing": [{"variety_id": setup["food"]["sunflower oil"].id}], "not_on_shelf": []}


def test_only_staff_can_see_the_packing_queue(client, db_with_sample_week):
    db = db_with_sample_week
    stop_the_clock_at(PACKING)
    assert client.get("/api/packing").status_code == 401
    log_in(client, db, make_student(db), PACKING)
    assert client.get("/api/packing").status_code == 401
    assert client.post("/api/packing/bags/1/packed", json={}).status_code == 401
    assert client.post("/api/packing/bags/1/unpack").status_code == 401


def test_the_queue_before_packing_starts(client, setup):
    stop_the_clock_at(MORNING)

    queue = client.get("/api/packing").json()

    assert queue["day"] == {
        "pickup_date": "2026-11-09",
        "packing_starts_at": "2026-11-09T12:00:00-03:30",
        "pickup_starts_at": "2026-11-09T15:30:00-03:30",
        "no_show_at": "2026-11-09T18:00:00-03:30",
        "can_pack": False,
        "why_not": "Packing for Monday, November 9 starts at 12:00 p.m., when booking closes. "
        "Until then, students can still cancel.",
    }
    assert [(bag["code"], bag["status"], bag["things"]) for bag in queue["bags"]] == [(setup["bag"].code, "booked", 1)]


def test_packing_a_bag_from_start_to_end(client, setup):
    bag_id, rice = setup["bag"].id, setup["food"]["rice"]

    bag = client.get(f"/api/packing/bags/{bag_id}").json()
    assert (bag["status"], bag["can_pack"], bag["sticky_note"]) == ("booked", True, [])
    assert [line["variety"] for line in bag["food"]] == ["Sunflower oil"]

    plan = client.post(f"/api/packing/bags/{bag_id}/plan", json=oil_missing(setup)).json()
    assert plan == {
        "substitutes": [{"rank": 1, "variety_id": rice.id, "outcome": "use", "replaces": "Sunflower oil"}],
        "sticky_note": ["Sunflower oil → White rice"],
        "in_bag": 1,
        "booked": 1,
        "uses": [rice.id],
    }

    response = client.post(f"/api/packing/bags/{bag_id}/packed", json=oil_missing(setup) | {"uses": plan["uses"]})
    assert response.status_code == 200
    packed = response.json()
    assert (packed["status"], packed["packed_by"], packed["packed_at"]) == ("packed", "Sam", "2026-11-09T12:30:00-03:30")
    assert packed["sticky_note"] == ["Sunflower oil → White rice"]
    assert packed["food"][0]["missing"] == 1
    assert packed["substitutes"][0]["replaced"] == "Sunflower oil"

    [queued] = client.get("/api/packing").json()["bags"]
    assert (queued["status"], queued["packed_by"]) == ("packed", "Sam")


def test_packing_twice_answers_409(client, setup):
    path = f"/api/packing/bags/{setup['bag'].id}/packed"
    assert client.post(path, json={}).status_code == 200

    again = client.post(path, json={})

    assert again.status_code == 409
    assert again.json() == {"detail": f"Bag {setup['bag'].code} is packed already, by Sam at 12:30 p.m."}


def test_undoing_packed(client, setup):
    """A bag packed by mistake goes back to "to pack". Undoing twice answers 409."""
    path = f"/api/packing/bags/{setup['bag'].id}"
    assert client.post(f"{path}/packed", json={}).json()["can_unpack"] is True

    undone = client.post(f"{path}/unpack")

    assert undone.status_code == 200
    assert (undone.json()["status"], undone.json()["can_pack"], undone.json()["can_unpack"]) == ("booked", True, False)
    again = client.post(f"{path}/unpack")
    assert again.status_code == 409
    assert again.json() == {"detail": f"Bag {setup['bag'].code} isn't packed."}


def test_a_plan_that_changed_answers_409(client, db, setup):
    """The page showed rice, then another bag took the last one."""
    setup["food"]["rice"].stock = 0
    db.flush()

    response = client.post(
        f"/api/packing/bags/{setup['bag'].id}/packed", json=oil_missing(setup) | {"uses": [setup["food"]["rice"].id]}
    )

    assert response.status_code == 409
    assert response.json()["detail"].startswith("The substitutes changed while you packed")


def test_food_that_ran_out_shows_on_the_bag_and_the_stock_page_until_counted(client, db, setup):
    """U7 on the pages: the next bag shows when the oil ran out, and the stock page asks for a count."""
    oil = setup["food"]["sunflower oil"]
    client.post(f"/api/packing/bags/{setup['bag'].id}/packed", json=oil_missing(setup) | {"uses": [setup["food"]["rice"].id]})

    def ran_out_on_stock_page():
        page = client.get("/api/stock").json()
        varieties = [v for c in page["categories"] for i in c["items"] for v in i["varieties"]]
        return next(v["ran_out_at"] for v in varieties if v["id"] == oil.id)

    assert ran_out_on_stock_page() == "2026-11-09T12:30:00-03:30"
    assert client.post(f"/api/varieties/{oil.id}/count", json={"on_shelf": 4}).status_code == 200
    assert ran_out_on_stock_page() is None


def test_a_bag_shows_nothing_about_the_student(client, db, setup):
    """P4: volunteers see the booking code and the food, never the ID hash or the account."""
    answers = [
        client.get("/api/packing").text,
        client.get(f"/api/packing/bags/{setup['bag'].id}").text,
        client.post(f"/api/packing/bags/{setup['bag'].id}/plan", json=oil_missing(setup)).text,
    ]

    for answer in answers:
        assert setup["student"].id_hash not in answer
        assert "student" not in answer


@pytest.mark.parametrize(
    "body",
    [
        {"missing": [{"variety_id": 1, "how_many": 0}]},
        {"missing": "oil"},
        {"uses": [1] * 101},
    ],
)
def test_a_badly_formed_request_answers_422(client, setup, body):
    response = client.post(f"/api/packing/bags/{setup['bag'].id}/packed", json=body)

    assert response.status_code == 422


def test_a_bag_that_does_not_exist_answers_404(client, setup):
    assert client.get("/api/packing/bags/999999").status_code == 404
    assert client.post("/api/packing/bags/999999/plan", json={}).status_code == 404


def test_no_pickup_days_coming_up(client, db_with_sample_week):
    db = db_with_sample_week
    log_in(client, db, make_staff(db), PACKING)
    stop_the_clock_at(PACKING)

    assert client.get("/api/packing").json() == {"day": None, "bags": [], "coming_up": []}


def test_the_next_days_bags_show_as_coming_up(client, setup, db_with_sample_week):
    """A bag for Thursday is listed while Monday is still being packed (13 Nov night):
    a volunteer can see it's there, and when packing for it starts."""
    db = db_with_sample_week
    thursday = make_pickup_day(db, MONDAY + timedelta(days=3))
    slot = db.scalars(select(Slot).where(Slot.pickup_day_id == thursday.id).order_by(Slot.starts_at)).first()
    wednesday_evening = datetime(2026, 11, 11, 21, 0, tzinfo=UTC)  # Thursday's booking is open
    other = make_student(db)
    booking_rules.hold_slot(db, other, slot.id, wednesday_evening)
    bag = booking_rules.book(db, other, [Choice(setup["food"]["rice"].id)], [], wednesday_evening)

    queue = client.get("/api/packing").json()

    assert queue["day"]["pickup_date"] == "2026-11-09"
    assert [b["code"] for b in queue["bags"]] == [setup["bag"].code]
    [coming] = queue["coming_up"]
    assert (coming["pickup_date"], coming["packing_starts_at"]) == ("2026-11-12", "2026-11-12T12:00:00-03:30")
    assert [(b["code"], b["status"], b["things"]) for b in coming["bags"]] == [(bag.code, "booked", 1)]


def test_days_with_no_bags_are_not_coming_up(client, setup, db_with_sample_week):
    make_pickup_day(db_with_sample_week, MONDAY + timedelta(days=3))

    assert client.get("/api/packing").json()["coming_up"] == []
