import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, text
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR, config
from app.deps import get_db
from app.main import app
from app.models import PickupHours
from tests.helpers import TEST_PICKUP_HOURS, add, make_settings


@pytest.fixture(scope="session")
def alembic_config():
    """Alembic, pointed at the test database instead of the working one."""
    alembic_config = AlembicConfig(BACKEND_DIR / "alembic.ini")
    alembic_config.set_main_option("sqlalchemy.url", config.test_database_url)
    return alembic_config


@pytest.fixture(scope="session")
def engine(alembic_config):
    """The test database, emptied and rebuilt from the migrations once per test run."""
    if config.test_database_url == config.database_url:
        pytest.exit("TEST_DATABASE_URL must point to a different database than DATABASE_URL")
    engine = create_engine(config.test_database_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    """A database session for one test. Everything it changes is undone afterwards."""
    with engine.connect() as connection:
        outer = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        yield session
        session.close()
        outer.rollback()


@pytest.fixture
def db_with_settings(db):
    """The sample settings, like 7 days for a setup code and 5 tries per 15 minutes."""
    make_settings(db)
    return db


@pytest.fixture
def db_with_sample_week(db):
    """The tests' own settings, with pickups on Monday and Thursday, 3:30 to 5:30 pm (TEST_PICKUP_HOURS)."""
    make_settings(db)
    for weekday, starts_at, ends_at in TEST_PICKUP_HOURS:
        add(db, PickupHours(weekday=weekday, starts_at=starts_at, ends_at=ends_at))
    return db


@pytest.fixture
def client(db):
    """Asks the server questions, the way the browser does.

    The server uses this test's database session, so it sees the rows the test
    made, and they are undone afterwards like any other test change.

    It pretends to use https, because login cookies are Secure: sent over https only.
    Like a browser, it keeps the cookies it is given and sends them back.
    """
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, base_url="https://testserver")
    app.dependency_overrides.clear()
