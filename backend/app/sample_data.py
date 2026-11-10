"""Fill an empty working database with the sample settings, food and pickup days.

Run from backend/:  .venv\\Scripts\\python -m app.sample_data

Everything here is made up. The real items and rules come from the Campus Food Bank later.
"""

from datetime import UTC, datetime, time

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Category, Item, PickupHours, Settings, Tag, Variety, VarietyTag
from app.services.photos import add_sample_photos
from app.services.pickup_days import make_days_ahead

# The sample values from CONSTRAINTS.md.
SAMPLE_SETTINGS = dict(
    pickup_gap_days=28,
    slot_minutes=10,
    slot_capacity=1,
    hold_minutes=10,
    item_limit=13,
    max_per_item=1,
    substitute_limit=5,
    booking_opens_days_before=1,
    booking_opens_time=time(17, 0),
    booking_closes_time=time(12, 0),
    no_show_time=time(18, 0),
    no_shows_count=False,
    retention_days=90,
    setup_code_days=7,
    login_tries=5,
    login_window_minutes=15,
)

# Monday and Thursday, 3:30 to 5:30 pm.
SAMPLE_PICKUP_HOURS = [(1, time(15, 30), time(17, 30)), (4, time(15, 30), time(17, 30))]

TAGS = ["Vegetarian", "Halal", "Gluten-free", "Contains nuts"]

# category -> item -> [(variety, stock, tags)]
SAMPLE_FOOD = {
    "Breakfast": {
        "Oats": [("Quick oats", 14, ["Vegetarian"]), ("Steel-cut oats", 6, ["Vegetarian"])],
        "Cereal": [("Corn flakes", 10, ["Vegetarian"]), ("Gluten-free cereal", 4, ["Vegetarian", "Gluten-free"])],
        "Peanut butter": [("Smooth peanut butter", 8, ["Vegetarian", "Contains nuts"])],
    },
    "Grains": {
        "Pasta": [("Spaghetti", 12, ["Vegetarian"]), ("Gluten-free pasta", 5, ["Vegetarian", "Gluten-free"])],
        "Rice": [("White rice", 15, ["Vegetarian", "Gluten-free"]), ("Brown rice", 6, ["Vegetarian", "Gluten-free"])],
    },
    "Protein": {
        "Canned chicken": [("Chunk chicken", 6, ["Halal"])],
        "Canned tuna": [("Tuna in water", 9, [])],
        "Chickpeas": [("Chickpeas (canned)", 1, ["Vegetarian", "Halal", "Gluten-free"])],
    },
    "Cooking": {
        "Cooking oil": [("Sunflower oil", 12, ["Vegetarian"]), ("Vegetable oil", 7, ["Vegetarian"])],
    },
}

# Extras aren't booked online, so their counts only guide "may be available" (E1, E2).
SAMPLE_EXTRAS = {
    "Bakery": {"Bread": [("White bread", 10, ["Vegetarian"]), ("Whole wheat bread", 8, ["Vegetarian"])]},
    "Dairy and eggs": {"Eggs": [("Dozen eggs", 6, ["Vegetarian", "Gluten-free"])]},
}


def add_food(db, food: dict, is_extra: bool, tags: dict[str, Tag]) -> None:
    for category_name, items in food.items():
        category = Category(name=category_name)
        db.add(category)
        db.flush()
        for item_name, varieties in items.items():
            item = Item(name=item_name, category_id=category.id, is_extra=is_extra)
            db.add(item)
            db.flush()
            for variety_name, stock, tag_names in varieties:
                variety = Variety(item_id=item.id, name=variety_name, stock=stock)
                db.add(variety)
                db.flush()
                for tag_name in tag_names:
                    db.add(VarietyTag(variety_id=variety.id, tag_id=tags[tag_name].id))


def add_sample_data(db, now: datetime) -> None:
    """The sample settings, pickup hours, tags, food and photos, without any pickup days.

    The demo (app.demo) uses this too, with its own clock.
    """
    db.add(Settings(**SAMPLE_SETTINGS))
    for weekday, starts_at, ends_at in SAMPLE_PICKUP_HOURS:
        db.add(PickupHours(weekday=weekday, starts_at=starts_at, ends_at=ends_at))
    tags = {name: Tag(name=name) for name in TAGS}
    db.add_all(tags.values())
    db.flush()

    add_food(db, SAMPLE_FOOD, is_extra=False, tags=tags)
    add_food(db, SAMPLE_EXTRAS, is_extra=True, tags=tags)
    add_sample_photos(db, now)


def main() -> None:
    now = datetime.now(UTC)
    with SessionLocal.begin() as db:
        if db.scalar(select(Settings)) is not None:
            raise SystemExit("The database already has data. Sample data goes into an empty database only.")
        add_sample_data(db, now)
        # The same week of pickup days the jobs script makes (S1).
        dates = [day.pickup_date for day in make_days_ahead(db, now)]

    print("Sample data added. Pickup days:", ", ".join(f"{d:%a %d %b}" for d in dates))


if __name__ == "__main__":
    main()
