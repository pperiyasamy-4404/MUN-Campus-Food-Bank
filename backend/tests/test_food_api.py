"""GET /api/food: the food on the shelf, by category and item."""

import pytest
from sqlalchemy import select

from app.models import Tag, Variety
from app.sample_data import add_food
from tests.helpers import add


@pytest.fixture
def shelf(db):
    """A small shelf, added in a muddled order so the tests can check the sorting."""
    tags = {name: add(db, Tag(name=name)) for name in ["Vegetarian", "Halal", "Gluten-free"]}
    add_food(
        db,
        {
            "Protein": {
                "Chickpeas": [("Chickpeas (canned)", 0, ["Vegetarian", "Halal", "Gluten-free"])],
                "Canned chicken": [("Chunk chicken", 6, ["Halal"]), ("Old chicken", 3, [])],
            },
            "Breakfast": {
                "Oats": [("Steel-cut oats", 6, ["Vegetarian"]), ("Quick oats", 14, ["Vegetarian"])],
            },
            "Cleaning": {"Soap": [("Bar soap", 5, [])]},
        },
        is_extra=False,
        tags=tags,
    )
    add_food(db, {"Bakery": {"Bread": [("White bread", 10, ["Vegetarian"])]}}, is_extra=True, tags=tags)
    # The food bank stopped getting these, so they're hidden, not deleted.
    for name in ["Old chicken", "Bar soap"]:
        db.scalars(select(Variety).where(Variety.name == name)).one().active = False
    db.flush()


def food(client):
    response = client.get("/api/food")
    assert response.status_code == 200
    return response.json()


def names(categories):
    """Category > item > variety, as one list of paths, to compare the order easily."""
    return [
        f"{category['name']} > {item['name']} > {variety['name']}"
        for category in categories
        for item in category["items"]
        for variety in item["varieties"]
    ]


def test_bookable_food_is_sorted_a_to_z(client, shelf):
    assert names(food(client)["bookable"]) == [
        "Breakfast > Oats > Quick oats",
        "Breakfast > Oats > Steel-cut oats",
        "Protein > Canned chicken > Chunk chicken",
        "Protein > Chickpeas > Chickpeas (canned)",
    ]


def test_hidden_varieties_are_left_out(client, shelf):
    """Old chicken is hidden. Soap had only one variety, so the whole Cleaning category goes too."""
    listed = names(food(client)["bookable"])

    assert not any("Old chicken" in path for path in listed)
    assert not any(path.startswith("Cleaning") for path in listed)


def without_ids(varieties):
    """Ids come from the database, so they differ from run to run."""
    assert all(isinstance(variety.pop("id"), int) for variety in varieties)
    return varieties


def test_bookable_food_shows_its_stock_even_at_zero(client, shelf):
    protein = food(client)["bookable"][1]

    assert without_ids(protein["items"][1]["varieties"]) == [
        {"name": "Chickpeas (canned)", "stock": 0, "tags": ["Gluten-free", "Halal", "Vegetarian"]}
    ]


def test_extras_are_listed_apart_with_no_count(client, shelf):
    """Extras only show as "may be available" (E1, E2), so the server doesn't send a count."""
    [bakery] = food(client)["extras"]
    [bread] = bakery["items"]
    assert (bakery["name"], bread["name"]) == ("Bakery", "Bread")
    assert without_ids(bread["varieties"]) == [{"name": "White bread", "stock": None, "tags": ["Vegetarian"]}]


def test_an_empty_shelf(client):
    assert food(client) == {"bookable": [], "extras": []}


def test_extras_with_none_left_are_left_out(client, shelf, db):
    """An extra that ran out isn't "available today" (E2)."""
    db.scalars(select(Variety).where(Variety.name == "White bread")).one().stock = 0
    db.flush()

    assert food(client)["extras"] == []
