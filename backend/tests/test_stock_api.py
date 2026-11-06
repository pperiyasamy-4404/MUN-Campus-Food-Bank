"""The staff stock page and its changes, used the way the browser uses them.

The counting and naming rules are in test_stock.py. These check who may use
which address, and what the page gets back.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Category, Tag, Variety
from tests.helpers import MONDAY, add, log_in, make_day, make_staff, make_variety, stop_the_clock_at

NOW = datetime(2026, 11, 8, 18, 0, tzinfo=UTC)  # Sunday 2:30 pm in St. John's


@pytest.fixture
def sam(client, db):
    """Sam, a volunteer, logged in on the test's browser."""
    stop_the_clock_at(NOW)
    sam = make_staff(db, "Sam")
    log_in(client, db, sam, NOW)
    return sam


@pytest.fixture
def alex(client, db):
    """Alex, the coordinator, logged in on the test's browser."""
    stop_the_clock_at(NOW)
    alex = make_staff(db, "Alex", role="coordinator")
    log_in(client, db, alex, NOW)
    return alex


@pytest.fixture
def protein(db):
    return add(db, Category(name="Protein"))


def the_page(client):
    response = client.get("/api/stock")
    assert response.status_code == 200
    return response.json()


# ---------- the page ----------


def test_only_staff_see_the_stock_page(client, db):
    stop_the_clock_at(NOW)
    assert client.get("/api/stock").status_code == 401


def test_the_page_lists_hidden_food_and_what_is_booked(client, db, sam):
    oats = make_variety(db, stock=6)
    oats.active = False
    vegetarian = add(db, Tag(name="Vegetarian"))
    client.put(f"/api/varieties/{oats.id}/tags", json={"tag_ids": [vegetarian.id]})

    [category] = the_page(client)["categories"]
    [item] = category["items"]

    assert item["varieties"] == [
        {
            "id": oats.id,
            "name": oats.name,
            "shown": False,
            "stock": 6,
            "booked_not_packed": 0,
            "tag_ids": [vegetarian.id],
            "counted_at": None,
            "counted_by": None,
        }
    ]
    assert the_page(client)["tags"] == [{"id": vegetarian.id, "name": "Vegetarian"}]


def test_empty_categories_are_listed_so_food_can_be_added_to_them(client, db, sam, protein):
    assert the_page(client)["categories"] == [{"id": protein.id, "name": "Protein", "items": []}]


def test_the_page_says_when_booking_opens_and_when_the_last_pickup_ended(client, db, sam):
    make_day(db, MONDAY - timedelta(days=7))  # last Monday: done
    make_day(db, MONDAY)  # tomorrow: booking opens at 5 pm today

    page = the_page(client)

    assert page["next_booking"] == {
        "pickup_date": "2026-11-09",
        "booking_opens_at": "2026-11-08T17:00:00-03:30",
        "booking_closes_at": "2026-11-09T12:00:00-03:30",
        "booking_status": "not_open_yet",
    }
    # Last Monday's no-show time, 6 pm: after that, counts are up to date.
    assert page["last_pickup_ended_at"] == "2026-11-02T18:00:00-03:30"


# ---------- counting (any staff) ----------


def test_a_volunteer_saves_a_count(client, db, sam):
    oats = make_variety(db, stock=3)

    response = client.post(f"/api/varieties/{oats.id}/count", json={"on_shelf": 14})

    assert response.status_code == 200
    counted = response.json()
    assert counted["short_by"] == 0
    assert counted["variety"]["stock"] == 14
    assert counted["variety"]["counted_by"] == "Sam"
    assert counted["variety"]["counted_at"] == "2026-11-08T14:30:00-03:30"


@pytest.mark.parametrize("on_shelf", [-1, 1000, "lots"])
def test_a_count_must_be_a_sensible_number(client, db, sam, on_shelf):
    oats = make_variety(db, stock=3)

    response = client.post(f"/api/varieties/{oats.id}/count", json={"on_shelf": on_shelf})

    assert response.status_code == 422
    [problem] = response.json()["detail"]
    assert problem["loc"] == ["body", "on_shelf"]
    if on_shelf != "lots":
        assert problem["msg"] == "Type a number from 0 to 999."


# ---------- adding food (any staff) ----------


def test_a_volunteer_adds_a_donation_of_something_new(client, db, sam, protein):
    halal = add(db, Tag(name="Halal"))

    response = client.post(
        "/api/items",
        json={
            "category_id": protein.id,
            "name": "  Canned   lentils ",
            "is_extra": False,
            "first_variety": {"name": "Red lentils", "tag_ids": [halal.id], "on_shelf": 12},
        },
    )

    assert response.status_code == 201
    [item] = the_page(client)["categories"][0]["items"]
    assert item["name"] == "Canned lentils"
    assert item["varieties"][0]["counted_by"] == "Sam"
    # Students see it straight away.
    food = client.get("/api/food").json()
    [lentils] = food["bookable"][0]["items"][0]["varieties"]
    assert (lentils["name"], lentils["stock"], lentils["tags"]) == ("Red lentils", 12, ["Halal"])


def test_adding_a_variety_and_a_taken_name(client, db, sam):
    oats = make_variety(db)

    added = client.post(f"/api/items/{oats.item_id}/varieties", json={"name": "Steel-cut", "on_shelf": 4})
    again = client.post(f"/api/items/{oats.item_id}/varieties", json={"name": "STEEL-CUT", "on_shelf": 4})

    assert added.status_code == 201
    assert again.status_code == 409
    assert "already has a variety called STEEL-CUT" in again.json()["detail"]


def test_a_volunteer_hides_and_shows_food(client, db, sam):
    oats = make_variety(db, stock=5)

    assert client.post(f"/api/varieties/{oats.id}/hide").status_code == 204
    assert client.get("/api/food").json()["bookable"] == []
    assert client.post(f"/api/varieties/{oats.id}/show").status_code == 204
    assert len(client.get("/api/food").json()["bookable"]) == 1


def test_a_name_needs_some_letters(client, db, sam, protein):
    response = client.post(
        "/api/items",
        json={
            "category_id": protein.id,
            "name": "   ",
            "is_extra": False,
            "first_variety": {"name": "x" * 61, "on_shelf": 1},
        },
    )

    assert response.status_code == 422
    messages = {tuple(problem["loc"]): problem["msg"] for problem in response.json()["detail"]}
    assert messages == {
        ("body", "name"): "Use 1 to 60 characters.",
        ("body", "first_variety", "name"): "Use 1 to 60 characters.",
    }


# ---------- the coordinator only ----------


@pytest.mark.parametrize(
    "method, address",
    [
        ("POST", "/api/categories"),
        ("POST", "/api/tags"),
        ("PATCH", "/api/categories/1"),
        ("PATCH", "/api/items/1"),
        ("PATCH", "/api/varieties/1"),
    ],
)
def test_only_the_coordinator_adds_categories_and_tags_and_fixes_names(client, db, sam, method, address):
    response = client.request(method, address, json={"name": "Anything"})

    assert response.status_code == 403
    assert response.json() == {"detail": "Only the coordinator can do this."}


def test_the_coordinator_adds_a_category_and_a_tag(client, db, alex):
    assert client.post("/api/categories", json={"name": "Snacks"}).status_code == 201
    assert client.post("/api/tags", json={"name": "Vegan"}).status_code == 201

    taken = client.post("/api/tags", json={"name": "vegan"})
    assert taken.status_code == 409
    assert taken.json() == {"detail": "There's already a tag called vegan."}
    assert db.scalar(select(Tag.name)) == "Vegan"


def test_the_coordinator_fixes_a_name(client, db, alex):
    oats = make_variety(db)

    assert client.patch(f"/api/varieties/{oats.id}", json={"name": "Quick oats"}).status_code == 204

    assert db.scalar(select(Variety.name).where(Variety.id == oats.id)) == "Quick oats"
    assert client.patch("/api/varieties/999999", json={"name": "Quick oats"}).status_code == 404
