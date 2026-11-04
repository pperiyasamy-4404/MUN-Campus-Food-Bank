import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR, config


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
