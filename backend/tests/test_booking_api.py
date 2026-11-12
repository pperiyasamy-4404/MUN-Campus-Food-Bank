"""The booking addresses, used the way the booking page uses them.

The rules are tested in test_booking.py. These check the answers the page gets,
and that everything here is the logged-in student's own.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Category, Item, Slot, Variety
from app.services.pickup_days import make_pickup_day
from tests.helpers import MONDAY, add, log_in, make_staff, make_student, stop_the_clock_at

OPEN = datetime(2026, 11, 8, 21, 0, tzinfo=UTC)  # Sunday 5:30 pm in St. John's


@pytest.fixture
def setup(client, db_with_sample_week):
    """Monday's pickup day, some food, and a student logged in on the test's browser."""
    db = db_with_sample_week
    stop_the_clock_at(OPEN)
    day = make_pickup_day(db, MONDAY)
    category = add(db, Category(name="Grains"))
    rice = add(db, Item(name="Rice", category_id=category.id))
    pasta = add(db, Item(name="Pasta", category_id=category.id))
    student = make_student(db)
    log_in(client, db, student, OPEN)
    return {
        "slots": list(db.scalars(select(Slot).where(Slot.pickup_day_id == day.id).order_by(Slot.starts_at))),
        "rice": add(db, Variety(item_id=rice.id, name="White rice", stock=5)),
        "spaghetti": add(db, Variety(item_id=pasta.id, name="Spaghetti", stock=5)),
        "student": student,
    }


def mine(client):
    response = client.get("/api/my-booking")
    assert response.status_code == 200
    return response.json()


def places_left(client, slot_id):
    [day] = client.get("/api/pickup-days").json()
    return next(slot["places_left"] for slot in day["slots"] if slot["id"] == slot_id)


def test_only_a_logged_in_student_has_a_booking_page(client, db_with_sample_week):
    stop_the_clock_at(OPEN)
    assert client.get("/api/my-booking").status_code == 401
    log_in(client, db_with_sample_week, make_staff(db_with_sample_week), OPEN)
    assert client.get("/api/my-booking").status_code == 401


def test_from_choosing_a_time_to_booked(client, db, setup):
    first = setup["slots"][0]
    assert mine(client)["booking"] is None
    assert mine(client)["limits"] == {"item_limit": 13, "max_per_item": 1, "substitute_limit": 5, "hold_minutes": 10}

    # Choose a time: it's held, with a countdown.
    held = client.post("/api/holds", json={"slot_id": first.id})
    assert held.status_code == 201
    assert held.json()["seconds_left"] == 600
    assert held.json()["starts_at"] == "2026-11-09T15:30:00-03:30"
    assert places_left(client, first.id) == 0  # nobody else is offered it

    # Two minutes later, press Book.
    stop_the_clock_at(OPEN + timedelta(minutes=2))
    assert mine(client)["hold"]["seconds_left"] == 480
    response = client.post(
        "/api/bookings",
        json={"items": [{"variety_id": setup["rice"].id}], "substitutes": [setup["spaghetti"].id]},
    )

    assert response.status_code == 201
    booking = response.json()
    assert booking["status"] == "booked"
    assert booking["starts_at"] == "2026-11-09T15:30:00-03:30"
    assert booking["items"] == [{"variety": "White rice", "item": "Rice", "quantity": 1}]
    assert booking["substitutes"] == [{"rank": 1, "variety": "Spaghetti", "item": "Pasta"}]
    assert (booking["can_cancel"], booking["cancel_until"]) == (True, "2026-11-09T12:00:00-03:30")
    assert mine(client)["booking"]["code"] == booking["code"]
    assert mine(client)["hold"] is None


def test_letting_go_of_a_time(client, db, setup):
    first = setup["slots"][0]
    client.post("/api/holds", json={"slot_id": first.id})

    assert client.delete("/api/holds").status_code == 204
    assert places_left(client, first.id) == 1


def test_a_refused_hold_says_why(client, db, setup):
    stop_the_clock_at(OPEN - timedelta(hours=1))

    response = client.post("/api/holds", json={"slot_id": setup["slots"][0].id})

    assert response.status_code == 400
    assert response.json() == {"detail": "Booking for Monday, November 9 opens Sunday, November 8 at 5:00 p.m."}


def test_pressing_book_twice(client, db, setup):
    client.post("/api/holds", json={"slot_id": setup["slots"][0].id})
    order = {"items": [{"variety_id": setup["rice"].id}]}
    code = client.post("/api/bookings", json=order).json()["code"]

    again = client.post("/api/bookings", json=order)

    assert again.status_code == 409
    assert again.json() == {"detail": f"You're booked already. Your code is {code}."}


def test_a_quantity_must_be_at_least_1(client, db, setup):
    client.post("/api/holds", json={"slot_id": setup["slots"][0].id})

    response = client.post("/api/bookings", json={"items": [{"variety_id": setup["rice"].id, "quantity": 0}]})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "items", 0, "quantity"]


def test_cancelling(client, db, setup):
    first = setup["slots"][0]
    client.post("/api/holds", json={"slot_id": first.id})
    client.post("/api/bookings", json={"items": [{"variety_id": setup["rice"].id}]})

    assert client.post("/api/my-booking/cancel").status_code == 204

    assert mine(client)["booking"] is None
    assert places_left(client, first.id) == 1
    assert client.post("/api/my-booking/cancel").status_code == 404


def test_the_gap_shows_on_the_booking_page(client, db, setup):
    setup["student"].last_pickup_on = MONDAY - timedelta(days=10)

    assert mine(client)["next_pickup_allowed_on"] == "2026-11-29"


def test_a_hold_that_ran_out_is_gone(client, db, setup):
    """410: the page goes back to choosing a time, whatever the words say."""
    client.post("/api/holds", json={"slot_id": setup["slots"][0].id})
    stop_the_clock_at(OPEN + timedelta(minutes=10))

    response = client.post("/api/bookings", json={"items": [{"variety_id": setup["rice"].id}]})

    assert response.status_code == 410
    assert response.json() == {"detail": "Your 10 minutes ran out, so the time was let go. Choose a time again."}
