"""The food bank's numbers: the one row of the settings table."""

from sqlalchemy.orm import Session

from app.models import Settings


def food_bank_settings(db: Session) -> Settings:
    settings = db.get(Settings, 1)
    if settings is None:
        raise LookupError("The settings row is missing")
    return settings
