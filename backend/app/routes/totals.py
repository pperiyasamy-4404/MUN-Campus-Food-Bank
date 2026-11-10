"""Weekly totals, for the coordinator (P12, R3).

Only numbers, and any number under 5 is sent as "fewer than 5". The real
small number never leaves the server, so it can't be read from the page's code
either. A small number can point to someone: "2 walk-ins on the week of
December 21" might be two people the coordinator knows.
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.deps import DB, CurrentCoordinator, Now
from app.models import Item
from app.services import totals

router = APIRouter(prefix="/api")

SMALLEST_SHOWN = 5

Shown = int | Literal["fewer than 5"]


def shown(number: int) -> Shown:
    """5 or more as it is; anything under 5, 0 included, as "fewer than 5" (P12)."""
    return number if number >= SMALLEST_SHOWN else "fewer than 5"


class ItemTotal(BaseModel):
    item: str
    given_out: Shown


class WeekOut(BaseModel):
    # The Monday the week starts on.
    week_starts_on: date
    picked_up: Shown
    walk_ins: Shown
    no_shows: Shown
    cancelled: Shown
    # Most given out first. The ones under 5 come last, A to Z, so their order says nothing.
    items: list[ItemTotal]


class TotalsPage(BaseModel):
    weeks: list[WeekOut]


@router.get("/totals")
def weekly_totals(coordinator: CurrentCoordinator, db: DB, now: Now) -> TotalsPage:
    found = totals.weeks(db, now)
    item_ids = {item_id for week in found.values() for item_id in week.given_out}
    names = dict(db.execute(select(Item.id, Item.name).where(Item.id.in_(item_ids))).all())
    return TotalsPage(
        weeks=[
            WeekOut(
                week_starts_on=starts_on,
                picked_up=shown(week.picked_up),
                walk_ins=shown(week.walk_ins),
                no_shows=shown(week.no_shows),
                cancelled=shown(week.cancelled),
                items=_items(week.given_out, names),
            )
            for starts_on, week in found.items()
        ]
    )


def _items(given_out: dict[int, int], names: dict[int, str]) -> list[ItemTotal]:
    big = sorted(
        ((names[item_id], count) for item_id, count in given_out.items() if count >= SMALLEST_SHOWN),
        key=lambda pair: (-pair[1], pair[0].lower()),
    )
    small = sorted(
        (names[item_id] for item_id, count in given_out.items() if 0 < count < SMALLEST_SHOWN), key=str.lower
    )
    return [ItemTotal(item=name, given_out=count) for name, count in big] + [
        ItemTotal(item=name, given_out="fewer than 5") for name in small
    ]
