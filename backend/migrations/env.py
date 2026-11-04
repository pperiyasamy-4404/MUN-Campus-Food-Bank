from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  (registers every table with Base.metadata)
from app.config import config as app_config
from app.db import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging, without switching off
# loggers the app or the tests have already set up.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Autogenerate compares the database with these tables.
target_metadata = Base.metadata


def database_url() -> str:
    """The tests pass the test database's URL in. Otherwise use DATABASE_URL from backend/.env."""
    return config.get_main_option("sqlalchemy.url") or app_config.database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode: write the SQL out instead of running it."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode, against the database itself."""
    connectable = create_engine(database_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
