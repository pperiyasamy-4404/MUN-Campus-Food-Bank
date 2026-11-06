"""P10: the ID number never appears in web addresses, logs or error messages.

One test takes an ID number through everything that touches it: the counter,
setup, a wrong password, a mistyped number, logging in. Every log line, every
answer and every database row is then searched for the number.
"""

import logging
from datetime import UTC, datetime

import pytest
from fastapi.routing import APIRoute
from pydantic import SecretStr
from sqlalchemy import text

from app.db import Base
from app.main import app
from app.security.keyed_hash import id_hash
from tests.helpers import ID_NUMBER, PASSWORD, stop_the_clock_at, volunteer_with_password

NOW = datetime(2026, 11, 8, 21, 0, tzinfo=UTC)
# A mistyped number, 8 digits: refused by the form check before anything else sees it.
TYPO = ID_NUMBER[:-1]


@pytest.fixture
def every_log_line(caplog):
    """Logs at every level, from every part, including each SQL statement and its values.

    Listed before `client` in a test, so the database connection is made after
    this and logs too.
    """
    caplog.set_level(logging.DEBUG)
    # SQLAlchemy sets its own logs to warnings only, so it needs telling separately.
    caplog.set_level(logging.DEBUG, logger="sqlalchemy.engine")
    return caplog


def test_the_id_number_is_never_in_an_answer_a_log_or_the_database(every_log_line, client, db_with_settings):
    db = db_with_settings
    stop_the_clock_at(NOW)
    volunteer_with_password(db, NOW, "Sam")
    counter = client
    answers = []

    def send(path, body):
        response = counter.post(path, json=body)
        answers.append(response)
        return response

    send("/api/staff/login", {"username": "Sam", "password": PASSWORD})
    code = send("/api/student-setup-codes", {"id_number": ID_NUMBER}).json()["setup_code"]
    send("/api/student-setup-codes", {"id_number": TYPO})
    send("/api/logout", {})
    send("/api/student/setup", {"id_number": TYPO, "setup_code": code, "new_password": PASSWORD})
    send("/api/student/setup", {"id_number": ID_NUMBER, "setup_code": "AAAA-AAAA", "new_password": PASSWORD})
    send("/api/student/setup", {"id_number": ID_NUMBER, "setup_code": code, "new_password": "short"})
    send("/api/student/setup", {"id_number": ID_NUMBER, "setup_code": code, "new_password": PASSWORD})
    send("/api/student/login", {"id_number": ID_NUMBER, "password": "wrong guess"})
    send("/api/student/login", {"id_number": TYPO, "password": PASSWORD})
    send("/api/student/login", {"id_number": f"{ID_NUMBER[:4]} {ID_NUMBER[4:]}", "password": PASSWORD})
    answers.append(counter.get("/api/me"))

    # Each kind of answer came up at least once, so the search below means something.
    assert {response.status_code for response in answers} >= {200, 201, 204, 401, 422}

    places = {
        "the web addresses": [str(response.request.url) for response in answers],
        "the answers": [response.text for response in answers],
        "the answer headers": [str(response.headers) for response in answers],
        "the logs": [record.getMessage() for record in every_log_line.records],
        "the database": every_row_as_text(db),
    }
    for place, texts in places.items():
        for number in [ID_NUMBER, TYPO]:
            assert not any(number in text for text in texts), f"the ID number is in {place}"
    # The logs really did include the SQL, or the search above would prove little.
    assert any("INSERT INTO students" in text for text in places["the logs"])
    # P4: volunteers don't see the hash either.
    assert not any(id_hash(ID_NUMBER) in text for text in places["the answers"])


def every_row_as_text(db) -> list[str]:
    """Every row of every table, written out by PostgreSQL as one line of text each."""
    rows = []
    for table in Base.metadata.sorted_tables:
        rows += db.scalars(text(f'SELECT t::text FROM "{table.name}" AS t')).all()
    return rows


def test_no_address_takes_a_secret_in_the_web_address():
    """ID numbers, passwords and setup codes only ever come in the body of a POST,
    so they can't end up in browser history or a server's access log."""
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        dependant = route.dependant
        outside_the_body = dependant.path_params + dependant.query_params + dependant.header_params
        for parameter in outside_the_body:
            assert parameter.field_info.annotation is not SecretStr, f"{route.path} takes {parameter.name}"
            for word in ["id_number", "password", "setup_code"]:
                assert word not in parameter.name, f"{route.path} takes {parameter.name}"
