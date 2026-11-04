from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, MetaData, Text, Time, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import config

# Every database rule gets a predictable name, like ck_varieties_stock_not_negative.
# Then an error says exactly which rule refused a change, and Alembic can find
# the rule again when it needs to change it.
NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        str: Text(),
        # timestamptz: one exact moment, shown in Newfoundland time (T1)
        datetime: DateTime(timezone=True),
        date: Date(),
        time: Time(),
    }


engine = create_engine(config.database_url)
SessionLocal = sessionmaker(engine)
