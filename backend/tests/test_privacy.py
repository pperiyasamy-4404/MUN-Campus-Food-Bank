"""P10: the ID number never appears in web addresses, logs or error messages.

One test takes an ID number through everything that touches it: the counter,
setup, a wrong password, a mistyped number, logging in. Every log line, every
answer and every database row is then searched for the number. A second test
does the same for walk-ins and handing over a bag (step 7).
"""

import logging
from datetime import UTC, datetime

import pytest
from fastapi.routing import APIRoute
from pydantic import SecretStr
from sqlalchemy import select, text

from app.db import Base
from app.main import app
from app.models import Category, Item, Slot, Student, Variety
from app.security.keyed_hash import id_hash
from app.services import booking as booking_rules
from app.services import packing
from app.services.booking import Choice
from app.services.pickup_days import make_pickup_day
from tests.helpers import (
    ID_NUMBER,
    MONDAY,
    OTHER_ID_NUMBER,
    PASSWORD,
    add,
    log_in,
    make_staff,
    stop_the_clock_at,
    volunteer_with_password,
)

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


def test_the_id_number_never_leaks_at_the_counter(every_log_line, client, db_with_sample_week):
    """The same search, for the counter: walk-ins and handing over a bag with the wrong card."""
    db = db_with_sample_week
    sunday = datetime(2026, 11, 8, 21, 0, tzinfo=UTC)  # booking open
    packing_time = datetime(2026, 11, 9, 16, 0, tzinfo=UTC)  # Monday 12:30 pm
    at_counter = datetime(2026, 11, 9, 19, 10, tzinfo=UTC)  # Monday 3:40 pm
    day = make_pickup_day(db, MONDAY)
    item = add(db, Item(name="Rice", category_id=add(db, Category(name="Grains")).id))
    rice = add(db, Variety(item_id=item.id, name="White rice", stock=5))
    # Someone else's packed bag, to try the wrong card on.
    other = add(db, Student(id_hash=id_hash(OTHER_ID_NUMBER), created_by_staff_id=make_staff(db).id))
    first = db.scalars(select(Slot).where(Slot.pickup_day_id == day.id)).first()
    booking_rules.hold_slot(db, other, first.id, sunday)
    bag = booking_rules.book(db, other, [Choice(rice.id)], [], sunday)
    packing.pack(db, bag.id, [], [], [], make_staff(db), packing_time)
    log_in(client, db, make_staff(db, "Sam"), at_counter)
    stop_the_clock_at(at_counter)
    answers = []

    def send(path, body):
        response = client.post(path, json=body)
        answers.append(response)
        return response

    send("/api/walk-ins/check", {"id_number": TYPO})
    send("/api/walk-ins/check", {"id_number": ID_NUMBER})
    send("/api/walk-ins", {"id_number": ID_NUMBER, "food": [{"variety_id": rice.id}]})
    send("/api/walk-ins", {"id_number": ID_NUMBER, "food": [{"variety_id": rice.id}]})
    send("/api/walk-ins", {"id_number": TYPO, "food": [{"variety_id": rice.id}]})
    send("/api/counter/find-by-card", {"id_number": TYPO})
    send("/api/counter/find-by-card", {"id_number": ID_NUMBER})
    send("/api/counter/pickups", {"code": bag.code, "id_number": ID_NUMBER})
    send("/api/counter/pickups", {"code": "ZZZ", "id_number": ID_NUMBER})

    assert {response.status_code for response in answers} >= {200, 201, 400, 404, 422}
    places = {
        "the web addresses": [str(response.request.url) for response in answers],
        "the answers": [response.text for response in answers],
        "the logs": [record.getMessage() for record in every_log_line.records],
        "the database": every_row_as_text(db),
    }
    for place, texts in places.items():
        for number in [ID_NUMBER, TYPO]:
            assert not any(number in text for text in texts), f"the ID number is in {place}"
    assert any("INSERT INTO walk_ins" in text for text in places["the logs"])
    assert not any(id_hash(ID_NUMBER) in text for text in places["the answers"])
