from app.models import Tag, Variety
from app.sample_data import SAMPLE_FOOD, TAGS, add_food
from tests.helpers import add


def test_sample_food_added_again_adds_nothing_and_changes_nothing(db):
    # app.add_sample_food runs this on a working database that has food already.
    tags = {name: add(db, Tag(name=name)) for name in TAGS}
    first = add_food(db, SAMPLE_FOOD, is_extra=False, tags=tags)
    assert {"Black beans", "Whole kernel corn", "Instant coffee", "Bran flakes"} <= set(first)

    coffee = db.query(Variety).filter_by(name="Instant coffee").one()
    coffee.stock = 3  # the food bank counted it since

    assert add_food(db, SAMPLE_FOOD, is_extra=False, tags=tags) == []
    assert db.query(Variety).filter_by(name="Instant coffee").count() == 1
    assert coffee.stock == 3


def test_gluten_free_only_on_food_that_really_is(db):
    # Decided 13 Nov: a sauce or malt can hide wheat, so those don't get the tag.
    gluten_free = {
        variety
        for items in SAMPLE_FOOD.values()
        for varieties in items.values()
        for variety, _, tags in varieties
        if "Gluten-free" in tags
    }
    assert not {"Rice crisps", "Beans in tomato sauce", "Tomato and basil", "Ramen cups (vegetable)"} & gluten_free
