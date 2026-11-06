"""Making accounts and giving setup codes: at the counter (R1) and by the coordinator (R3).

A setup code is shown once, in the answer to the request that made it. It is
never saved, so nobody can look it up again later, not even the coordinator.
"""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.deps import DB, CurrentCoordinator, CurrentStaff, Now
from app.models import SetupCode, Staff
from app.security.inputs import IdNumber, NewUsername
from app.services import accounts
from app.services.pickup_days import NEWFOUNDLAND

router = APIRouter(prefix="/api")


# ---------- what comes in ----------


class StudentCard(BaseModel):
    """The number on the MUN card the volunteer has just checked."""

    id_number: IdNumber


class NewVolunteer(BaseModel):
    username: NewUsername


# ---------- what goes out ----------


class SetupCodeOut(BaseModel):
    """Read it out or write it down. There is no way to see it again."""

    setup_code: str
    expires_at: datetime
    # True when this made the account, so the screen can say "New account".
    new_account: bool


class VolunteerOut(BaseModel):
    id: int
    username: str
    # False until they use their setup code to choose a password.
    password_set: bool
    # When their unused setup code runs out, if they have one.
    setup_code_expires_at: datetime | None
    switched_off_at: datetime | None


def setup_code_out(issued: accounts.IssuedCode) -> SetupCodeOut:
    return SetupCodeOut(
        setup_code=issued.code,
        expires_at=issued.expires_at.astimezone(NEWFOUNDLAND),
        new_account=issued.new_account,
    )


def volunteer_out(volunteer: Staff, code_expires_at: datetime | None) -> VolunteerOut:
    return VolunteerOut(
        id=volunteer.id,
        username=volunteer.username,
        password_set=volunteer.password_hash is not None,
        setup_code_expires_at=code_expires_at.astimezone(NEWFOUNDLAND) if code_expires_at else None,
        switched_off_at=volunteer.disabled_at.astimezone(NEWFOUNDLAND) if volunteer.disabled_at else None,
    )


def setup_code_expiry(db: DB, volunteer: Staff) -> datetime | None:
    return db.scalar(select(SetupCode.expires_at).where(SetupCode.staff_id == volunteer.id))


# ---------- at the counter ----------


@router.post("/student-setup-codes", status_code=201)
def give_student_setup_code(card: StudentCard, staff: CurrentStaff, db: DB, now: Now) -> SetupCodeOut:
    """A new card gets an account and a code. A card with an account gets a new code,
    which is how a forgotten password is reset (R1).

    The answer never includes the ID number or its hash (P4).
    """
    issued = accounts.give_student_setup_code(db, card.id_number.get_secret_value(), staff, now)
    db.commit()
    return setup_code_out(issued)


# ---------- the coordinator's volunteer list ----------


@router.get("/volunteers")
def list_volunteers(coordinator: CurrentCoordinator, db: DB) -> list[VolunteerOut]:
    """Every volunteer, switched off ones too, in alphabetical order."""
    rows = db.execute(
        select(Staff, SetupCode.expires_at)
        .outerjoin(SetupCode, SetupCode.staff_id == Staff.id)
        .where(Staff.role == "volunteer")
        .order_by(func.lower(Staff.username))
    ).all()
    return [volunteer_out(volunteer, code_expires_at) for volunteer, code_expires_at in rows]


class VolunteerWithCode(BaseModel):
    """A volunteer just added or switched back on, and the setup code to give them."""

    volunteer: VolunteerOut
    code: SetupCodeOut


@router.post("/volunteers", status_code=201)
def add_volunteer(details: NewVolunteer, coordinator: CurrentCoordinator, db: DB, now: Now) -> VolunteerWithCode:
    volunteer, issued = accounts.add_volunteer(db, details.username, coordinator, now)
    db.commit()
    return VolunteerWithCode(volunteer=volunteer_out(volunteer, issued.expires_at), code=setup_code_out(issued))


@router.post("/volunteers/{staff_id}/setup-code", status_code=201)
def give_volunteer_setup_code(staff_id: int, coordinator: CurrentCoordinator, db: DB, now: Now) -> SetupCodeOut:
    """For a volunteer who lost their code or forgot their password.

    Their old password keeps working until they use the new code.
    """
    volunteer = accounts.volunteer_with_id(db, staff_id)
    issued = accounts.give_volunteer_setup_code(db, volunteer, coordinator, now)
    db.commit()
    return setup_code_out(issued)


@router.post("/volunteers/{staff_id}/switch-off")
def switch_off_volunteer(staff_id: int, coordinator: CurrentCoordinator, db: DB, now: Now) -> VolunteerOut:
    """Logs them out everywhere and stops them logging in, until they're switched back on.
    Asking twice does nothing more."""
    volunteer = accounts.volunteer_with_id(db, staff_id)
    accounts.switch_off_volunteer(db, volunteer, coordinator, now)
    db.commit()
    return volunteer_out(volunteer, None)


@router.post("/volunteers/{staff_id}/switch-on", status_code=201)
def switch_on_volunteer(staff_id: int, coordinator: CurrentCoordinator, db: DB, now: Now) -> VolunteerWithCode:
    """For a volunteer who comes back: same account, a new setup code, and their old password no longer works."""
    volunteer = accounts.volunteer_with_id(db, staff_id)
    issued = accounts.switch_on_volunteer(db, volunteer, coordinator, now)
    db.commit()
    return VolunteerWithCode(volunteer=volunteer_out(volunteer, issued.expires_at), code=setup_code_out(issued))
