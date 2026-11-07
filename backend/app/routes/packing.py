"""The packing queue and packing one bag, for staff (K1, U4-U8, R2).

Volunteers see each bag's code and food, never anything about the student (P4).
"""

from datetime import date, datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.deps import DB, CurrentStaff, Now
from app.models import Booking, PickupDay, Slot, Staff
from app.services import packing
from app.services.packing import Missing, Outcome
from app.services.pickup_days import NEWFOUNDLAND

router = APIRouter(prefix="/api")


def _newfoundland(moment: datetime | None) -> datetime | None:
    return moment.astimezone(NEWFOUNDLAND) if moment else None


# ---------- the queue ----------


class QueueDay(BaseModel):
    pickup_date: date
    # Packing starts when booking closes (K1).
    packing_starts_at: datetime
    # The first pickup time, if the day has any.
    pickup_starts_at: datetime | None
    no_show_at: datetime
    can_pack: bool
    # Why not, in words, like "Packing for Monday, November 9 starts at 12:00 p.m., ..."
    why_not: str | None


class QueueBag(BaseModel):
    id: int
    code: str
    starts_at: datetime
    status: str
    things: int
    # Booked food that another volunteer found none of on the shelf (U7).
    ran_out: list[str]
    packed_at: datetime | None
    packed_by: str | None


class PackingQueue(BaseModel):
    # The day being packed now, or packed next. None if no pickup days are coming up.
    day: QueueDay | None
    bags: list[QueueBag]


@router.get("/packing")
def packing_queue(staff: CurrentStaff, db: DB, now: Now) -> PackingQueue:
    day = packing.packing_day(db, now)
    if day is None:
        return PackingQueue(day=None, bags=[])
    why_not = packing.why_not_pack(day, now)
    return PackingQueue(
        day=QueueDay(
            pickup_date=day.pickup_date,
            packing_starts_at=_newfoundland(day.booking_closes_at),
            pickup_starts_at=_newfoundland(db.scalar(select(func.min(Slot.starts_at)).where(Slot.pickup_day_id == day.id))),
            no_show_at=_newfoundland(day.no_show_at),
            can_pack=why_not is None,
            why_not=why_not,
        ),
        bags=[
            QueueBag(
                id=bag.booking.id,
                code=bag.booking.code,
                starts_at=_newfoundland(bag.starts_at),
                status=bag.booking.status,
                things=bag.things,
                ran_out=bag.ran_out,
                packed_at=_newfoundland(bag.booking.packed_at),
                packed_by=bag.packed_by,
            )
            for bag in packing.queue(db, day)
        ],
    )


# ---------- one bag ----------


class BagFood(BaseModel):
    variety_id: int
    variety: str
    item: str
    quantity: int
    # How many weren't on the shelf. Saved when the bag is packed, 0 before.
    missing: int
    # When a volunteer found none on the shelf, maybe while packing another bag (U7).
    ran_out_at: datetime | None


class BagSubstitute(BaseModel):
    rank: int
    variety_id: int
    variety: str
    item: str
    # Once packed: the booked food it went in for.
    replaced: str | None


class Bag(BaseModel):
    id: int
    code: str
    pickup_date: date
    starts_at: datetime
    status: str
    packed_at: datetime | None
    packed_by: str | None
    can_pack: bool
    why_not: str | None
    # Packed by mistake? It can be undone until the bag is handed over (decided 7 Nov).
    can_unpack: bool
    food: list[BagFood]
    substitutes: list[BagSubstitute]
    # Once packed: what was written on the sticky note (U8).
    sticky_note: list[str]


def bag_out(booking: Booking, db: DB, now: datetime) -> Bag:
    day = db.get(PickupDay, booking.pickup_day_id)
    slot = db.get(Slot, booking.slot_id)
    food = packing.food_in(db, booking)
    substitutes = packing.substitutes_of(db, booking)
    names = {line.variety.id: line.variety.name for line in food}
    problem = packing.why_not_this_bag(db, booking, day, now)
    packer = db.get(Staff, booking.packed_by_staff_id) if booking.packed_by_staff_id else None
    return Bag(
        id=booking.id,
        code=booking.code,
        pickup_date=day.pickup_date,
        starts_at=_newfoundland(slot.starts_at),
        status=booking.status,
        packed_at=_newfoundland(booking.packed_at),
        packed_by=packer.username if packer else None,
        can_pack=problem is None,
        why_not=problem.message if problem else None,
        can_unpack=packing.why_not_unpack(booking, day, now) is None,
        food=[
            BagFood(
                variety_id=line.variety.id,
                variety=line.variety.name,
                item=line.item.name,
                quantity=line.row.quantity,
                missing=line.row.missing,
                ran_out_at=_newfoundland(line.variety.ran_out_at),
            )
            for line in food
        ],
        substitutes=[
            BagSubstitute(
                rank=line.row.rank,
                variety_id=line.variety.id,
                variety=line.variety.name,
                item=line.item.name,
                replaced=names.get(line.row.replaces_variety_id) if line.row.replaces_variety_id else None,
            )
            for line in substitutes
        ],
        sticky_note=packing.saved_note(food, substitutes) if booking.packed_at else [],
    )


@router.get("/packing/bags/{booking_id}")
def one_bag(booking_id: int, staff: CurrentStaff, db: DB, now: Now) -> Bag:
    return bag_out(packing.find_bag(db, booking_id), db, now)


# ---------- the plan, and Packed ----------


class MissingIn(BaseModel):
    variety_id: int
    # How many weren't on the shelf. Leave it out for "none at all".
    how_many: int | None = Field(default=None, ge=1, le=99)


class Findings(BaseModel):
    # Booked food that isn't on the shelf, in the order the volunteer found out.
    missing: list[MissingIn] = Field(default=[], max_length=100)
    # Substitutes the volunteer looked for and found none of.
    not_on_shelf: list[int] = Field(default=[], max_length=100)

    def missing_food(self) -> list[Missing]:
        return [Missing(found.variety_id, found.how_many) for found in self.missing]


class SubstitutePlan(BaseModel):
    rank: int
    variety_id: int
    outcome: Outcome
    # For "use": the booked food it goes in for.
    replaces: str | None


class PlanOut(BaseModel):
    substitutes: list[SubstitutePlan]
    sticky_note: list[str]
    # Things in the bag once it's packed, and things booked. Fewer in the bag
    # means the student chooses the rest at the counter (U6).
    in_bag: int
    booked: int
    # The substitutes to put in, best first. The page sends these back with Packed.
    uses: list[int]


def plan_out(plan: packing.Plan) -> PlanOut:
    names = plan.names()
    replaces = {used: names[gap] for gap, used in plan.refill.swaps if used is not None}
    return PlanOut(
        substitutes=[
            SubstitutePlan(
                rank=line.row.rank,
                variety_id=line.variety.id,
                outcome=plan.refill.outcomes[line.variety.id],
                replaces=replaces.get(line.variety.id),
            )
            for line in plan.substitutes
        ],
        sticky_note=plan.sticky_note(),
        in_bag=plan.in_bag(),
        booked=plan.booked(),
        uses=plan.refill.used,
    )


@router.post("/packing/bags/{booking_id}/plan")
def what_goes_in(booking_id: int, findings: Findings, staff: CurrentStaff, db: DB, now: Now) -> PlanOut:
    """Works out the refill for what the volunteer found so far. Saves nothing."""
    return plan_out(packing.plan(db, booking_id, findings.missing_food(), findings.not_on_shelf, now))


class PackedIn(Findings):
    # What the plan said to put in. If it has changed since, Packed is refused (409).
    uses: list[int] = Field(default=[], max_length=100)


@router.post("/packing/bags/{booking_id}/packed")
def packed(booking_id: int, details: PackedIn, staff: CurrentStaff, db: DB, now: Now) -> Bag:
    packing.pack(db, booking_id, details.missing_food(), details.not_on_shelf, details.uses, staff, now)
    db.commit()
    return bag_out(packing.find_bag(db, booking_id), db, now)


@router.post("/packing/bags/{booking_id}/unpack")
def undo_packed(booking_id: int, staff: CurrentStaff, db: DB, now: Now) -> Bag:
    """Packed by mistake: the bag goes back to "to pack", and its substitutes back on the shelf."""
    packing.unpack(db, booking_id, staff, now)
    db.commit()
    return bag_out(packing.find_bag(db, booking_id), db, now)
