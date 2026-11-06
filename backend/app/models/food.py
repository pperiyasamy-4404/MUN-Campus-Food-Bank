from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Identity, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Category(Base):
    """Breakfast, Protein, Bakery... Each item has one (I2)."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    name: Mapped[str]

    __table_args__ = (Index("uq_categories_name_lower", text("lower(name)"), unique=True),)


class Item(Base):
    """A kind of food, like oats or canned chicken (I1).

    The category is here, not on each variety, so quick oats and steel-cut oats
    can never end up in different categories (I2).
    """

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    name: Mapped[str]
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    # Extras like bread aren't booked online and don't count toward the item limit (E1).
    is_extra: Mapped[bool] = mapped_column(server_default=text("false"))

    __table_args__ = (Index("uq_items_name_lower", text("lower(name)"), unique=True),)


class Variety(Base):
    """What's on the shelf, like quick oats. Stock is counted here (I1)."""

    __tablename__ = "varieties"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    name: Mapped[str]
    # How many more students can book it. Booking takes one off (I5),
    # cancelling or a no-show puts it back (I6).
    stock: Mapped[int] = mapped_column(server_default=text("0"))
    # Hidden, not deleted, when the food bank stops getting it: old bookings still point here.
    active: Mapped[bool] = mapped_column(server_default=text("true"))
    # When the shelf was last counted, and by whom, so volunteers can see what
    # still needs counting before booking opens (I8). Empty until the first count.
    counted_at: Mapped[datetime | None]
    counted_by_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))

    __table_args__ = (
        # Even when two students take the last one at the same moment (I4).
        CheckConstraint("stock >= 0", name="stock_not_negative"),
        # A count always says who made it.
        CheckConstraint("(counted_at IS NULL) = (counted_by_staff_id IS NULL)", name="count_has_a_counter"),
        Index("uq_varieties_item_id_name_lower", "item_id", text("lower(name)"), unique=True),
    )


class Tag(Base):
    """Dietary tags: vegetarian, halal, gluten-free, contains nuts (I2).

    A table, not yes/no columns, so the coordinator can add one without a code change.
    """

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    name: Mapped[str]

    __table_args__ = (Index("uq_tags_name_lower", text("lower(name)"), unique=True),)


class VarietyTag(Base):
    """Says "this variety has this tag". The pair is the primary key, so each pair appears once."""

    __tablename__ = "variety_tags"

    variety_id: Mapped[int] = mapped_column(
        ForeignKey("varieties.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
