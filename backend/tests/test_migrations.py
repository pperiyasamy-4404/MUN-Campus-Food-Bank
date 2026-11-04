from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

import app.models  # noqa: F401  (registers every table with Base.metadata)
from app.db import Base


def test_the_migrations_match_the_table_classes(engine):
    """Fails if a table class changes but nobody made a migration for it."""
    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert differences == []


def test_the_migrations_can_be_undone_and_run_again(engine, alembic_config):
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
