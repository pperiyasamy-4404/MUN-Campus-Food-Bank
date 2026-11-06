"""The setup script that makes the first coordinator (R3), run against the test database."""

import re
from contextlib import contextmanager

import pytest
from sqlalchemy import select

from app import first_coordinator
from app.models import SetupCode, Staff
from app.security.setup_codes import setup_code_hash


@pytest.fixture
def run(db, monkeypatch, capsys):
    """Runs the script as if typed in the terminal. Gives back its exit code and what it printed."""

    @contextmanager
    def test_database():
        yield db

    monkeypatch.setattr(first_coordinator, "SessionLocal", test_database)

    def run_with(*arguments: str) -> tuple[int, str, str]:
        exit_code = first_coordinator.main(list(arguments))
        printed = capsys.readouterr()
        return exit_code, printed.out, printed.err

    return run_with


def test_it_makes_the_coordinator_and_prints_the_code_once(run, db_with_settings):
    exit_code, printed, _ = run("Alex")

    assert exit_code == 0
    assert "Made the coordinator account." in printed
    [code] = re.findall(r"Setup code: (\S+)", printed)
    alex = db_with_settings.scalar(select(Staff))
    assert (alex.username, alex.role) == ("Alex", "coordinator")
    # What was printed is the code that works, and only its HMAC was saved.
    assert db_with_settings.scalar(select(SetupCode.code_hash)) == setup_code_hash(code)


def test_run_again_it_gives_a_new_code_and_refuses_a_second_coordinator(run, db_with_settings):
    run("Alex")

    exit_code, printed, _ = run("alex")
    assert exit_code == 0
    assert "Gave the coordinator a new setup code." in printed

    exit_code, _, problem = run("Jordan")
    assert exit_code == 1
    assert "already set up: Alex" in problem


def test_it_refuses_a_username_that_does_not_fit(run, db_with_settings):
    exit_code, _, problem = run("<script>")

    assert exit_code == 1
    assert "letters, numbers, spaces, dots or dashes" in problem


def test_it_says_so_when_the_settings_are_missing(run, db):
    exit_code, _, problem = run("Alex")

    assert exit_code == 1
    assert "settings aren't in the database yet" in problem
    assert db.scalar(select(Staff)) is None
