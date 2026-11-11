"""The login and account web addresses, used the way the browser uses them.

The rules themselves are tested in test_accounts.py. These check what only the
web side does: cookies, who may use which address, how long a login lasts, and
the answers the page gets back.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import LoginSession
from app.security.sessions import COOKIE
from app.security.wrong_tries import DEVICE_COOKIE
from app.services import accounts
from tests.helpers import (
    ID_NUMBER,
    PASSWORD,
    make_staff,
    stop_the_clock_at,
    student_with_password,
    volunteer_with_password,
)

NOW = datetime(2026, 11, 8, 21, 0, tzinfo=UTC)


@pytest.fixture
def db(db_with_settings):
    """Every test here needs the settings: setup code lifetime and wrong tries."""
    stop_the_clock_at(NOW)
    return db_with_settings


def another_browser() -> TestClient:
    """A second browser, with its own cookies, using the same test database."""
    return TestClient(app, base_url="https://testserver")


def log_in_student(client, id_number=ID_NUMBER, password=PASSWORD):
    return client.post("/api/student/login", json={"id_number": id_number, "password": password})


def log_in_staff(client, username="Sam", password=PASSWORD):
    return client.post("/api/staff/login", json={"username": username, "password": password})


def me(client):
    response = client.get("/api/me")
    assert response.status_code == 200
    return response.json()


def cookie_lines(response) -> dict[str, str]:
    """The Set-Cookie lines of an answer, by cookie name."""
    return {line.split("=", 1)[0]: line for line in response.headers.get_list("set-cookie")}


# ---------- a student, from the counter to logged in ----------


def test_a_student_sets_up_their_account_and_stays_logged_in(client, db):
    counter = another_browser()
    assert log_in_staff(counter, "Sam").status_code == 401  # no account yet
    volunteer_with_password(db, NOW, "Sam")
    assert log_in_staff(counter, "Sam").status_code == 200

    given = counter.post("/api/student-setup-codes", json={"id_number": ID_NUMBER})
    assert given.status_code == 201
    assert given.json()["new_account"] is True
    assert given.json()["expires_at"] == "2026-11-15T17:30:00-03:30"  # 7 days, in Newfoundland time

    # Later, on the student's own phone. Small letters and a space are fine.
    typed_code = given.json()["setup_code"].lower().replace("-", " ")
    response = client.post(
        "/api/student/setup",
        json={"id_number": ID_NUMBER, "setup_code": typed_code, "new_password": PASSWORD},
    )

    assert response.status_code == 200
    assert response.json() == {"kind": "student", "password_reset_at": None}
    assert me(client) == {"kind": "student", "password_reset_at": None}


def test_login_cookies_can_not_be_read_by_the_page_or_sent_by_other_websites(client, db):
    student_with_password(db, NOW)

    cookies = cookie_lines(log_in_student(client))

    for name in [COOKIE, DEVICE_COOKIE]:
        line = cookies[name].lower()
        assert "httponly" in line
        assert "secure" in line
        assert "samesite=strict" in line
    assert "max-age=2592000" in cookies[COOKIE].lower()  # 30 days


def test_the_session_table_keeps_a_hash_of_the_ticket_not_the_ticket(client, db):
    student_with_password(db, NOW)
    log_in_student(client)

    ticket = client.cookies[COOKIE]
    [login] = db.scalars(select(LoginSession)).all()
    assert login.token_hash != ticket
    assert ticket not in login.token_hash


def test_a_reset_password_shows_its_date_and_logs_out_the_old_browser(client, db):
    student = student_with_password(db, NOW)
    flatmates_laptop = another_browser()
    log_in_student(flatmates_laptop)
    reset_at = NOW + timedelta(days=2)
    stop_the_clock_at(reset_at)
    issued = accounts.give_student_setup_code(db, ID_NUMBER, make_staff(db), reset_at)

    response = client.post(
        "/api/student/setup",
        json={"id_number": ID_NUMBER, "setup_code": issued.code, "new_password": "a brand new phrase"},
    )

    assert response.json()["password_reset_at"] == "2026-11-10T17:30:00-03:30"
    assert student.password_reset_at == reset_at
    assert me(flatmates_laptop) is None


def test_logging_out_ends_the_login_on_the_server_too(client, db):
    student_with_password(db, NOW)
    log_in_student(client)
    ticket = client.cookies[COOKIE]

    assert client.post("/api/logout").status_code == 204

    assert me(client) is None
    # Even a copy of the old ticket logs in to nothing.
    assert me(another_browser_with(ticket)) is None


def another_browser_with(ticket: str) -> TestClient:
    browser = another_browser()
    browser.cookies.set(COOKIE, ticket)
    return browser


def test_nobody_is_logged_in_without_a_cookie_or_with_a_made_up_one(client, db):
    assert me(client) is None
    assert me(another_browser_with("made-up-ticket")) is None


# ---------- how long a login lasts ----------


def test_a_student_stays_logged_in_30_days_after_their_last_visit(client, db):
    student_with_password(db, NOW)
    log_in_student(client)

    # Back 20 days later: the 30 days start again.
    stop_the_clock_at(NOW + timedelta(days=20))
    response = client.get("/api/me")
    assert "max-age=2592000" in cookie_lines(response)[COOKIE].lower()

    stop_the_clock_at(NOW + timedelta(days=49))
    assert me(client) is not None
    stop_the_clock_at(NOW + timedelta(days=79))
    assert me(client) is None


def test_a_students_login_moves_on_at_most_once_a_day(client, db):
    """So not every visit writes to the database."""
    student_with_password(db, NOW)
    log_in_student(client)
    [login] = db.scalars(select(LoginSession)).all()

    stop_the_clock_at(NOW + timedelta(hours=23))
    response = client.get("/api/me")

    assert COOKIE not in cookie_lines(response)
    assert login.expires_at == NOW + timedelta(days=30)


def test_a_staff_login_ends_12_hours_after_logging_in_however_busy_the_shift(client, db):
    volunteer_with_password(db, NOW, "Sam")
    log_in_staff(client)

    stop_the_clock_at(NOW + timedelta(hours=11, minutes=59))
    assert me(client) == {"kind": "staff", "username": "Sam", "role": "volunteer"}
    stop_the_clock_at(NOW + timedelta(hours=12))
    assert me(client) is None


# ---------- who may use which address ----------


def test_only_staff_can_give_a_student_a_setup_code(client, db):
    student_with_password(db, NOW, id_number="202300001")

    def give(browser):
        return browser.post("/api/student-setup-codes", json={"id_number": ID_NUMBER})

    assert give(client).status_code == 401
    log_in_student(client, "202300001")
    assert give(client).status_code == 401

    counter = another_browser()
    volunteer_with_password(db, NOW, "Sam")
    log_in_staff(counter, "Sam")
    assert give(counter).status_code == 201


@pytest.mark.parametrize(
    "method, address",
    [
        ("GET", "/api/volunteers"),
        ("POST", "/api/volunteers"),
        ("POST", "/api/volunteers/1/setup-code"),
        ("POST", "/api/volunteers/1/switch-off"),
        ("POST", "/api/volunteers/1/switch-on"),
        ("POST", "/api/volunteers/1/make-coordinator"),
        ("POST", "/api/volunteers/1/make-volunteer"),
    ],
)
def test_only_the_coordinator_manages_volunteers(client, db, method, address):
    assert client.request(method, address, json={"username": "Pat"}).status_code == 401
    volunteer_with_password(db, NOW, "Sam")
    log_in_staff(client, "Sam")

    response = client.request(method, address, json={"username": "Pat"})

    assert response.status_code == 403
    assert response.json() == {"detail": "Only a coordinator can do this."}


def log_in_coordinator(client, db):
    """Alex, set up by the setup script, with a password chosen from its code."""
    issued = accounts.set_up_first_coordinator(db, "Alex", NOW)
    accounts.set_staff_password(db, "Alex", issued.code, PASSWORD, None, NOW)
    assert log_in_staff(client, "Alex").status_code == 200


def test_the_coordinator_adds_lists_and_switches_off_volunteers(client, db):
    log_in_coordinator(client, db)

    added = client.post("/api/volunteers", json={"username": "  Pat   O'Brien "})
    assert added.status_code == 201
    pat = added.json()["volunteer"]
    assert pat["username"] == "Pat O'Brien"
    assert pat["password_set"] is False
    assert pat["setup_code_expires_at"] == added.json()["code"]["expires_at"]

    # Pat chooses a password on their own phone.
    pats_phone = another_browser()
    setup = pats_phone.post(
        "/api/staff/setup",
        json={"username": "pat o'brien", "setup_code": added.json()["code"]["setup_code"], "new_password": PASSWORD},
    )
    assert setup.json() == {"kind": "staff", "username": "Pat O'Brien", "role": "volunteer"}

    alex, listed = client.get("/api/volunteers").json()
    assert (alex["username"], alex["role"], alex["you"]) == ("Alex", "coordinator", True)
    assert (listed["role"], listed["you"]) == ("volunteer", False)
    assert (listed["password_set"], listed["setup_code_expires_at"], listed["switched_off_at"]) == (True, None, None)

    switched_off = client.post(f"/api/volunteers/{pat['id']}/switch-off")
    assert switched_off.json()["switched_off_at"] == "2026-11-08T17:30:00-03:30"
    # Logged out at once, on their own phone too.
    assert me(pats_phone) is None
    assert log_in_staff(pats_phone, "Pat O'Brien").status_code == 401


def test_the_coordinator_switches_a_volunteer_back_on(client, db):
    log_in_coordinator(client, db)
    sam = volunteer_with_password(db, NOW, "Sam")
    client.post(f"/api/volunteers/{sam.id}/switch-off")

    response = client.post(f"/api/volunteers/{sam.id}/switch-on")

    assert response.status_code == 201
    back = response.json()
    assert (back["volunteer"]["switched_off_at"], back["volunteer"]["password_set"]) == (None, False)
    assert back["volunteer"]["setup_code_expires_at"] == back["code"]["expires_at"]
    # Asked again, it's refused, so it can never undo a password Sam has chosen since.
    again = client.post(f"/api/volunteers/{sam.id}/switch-on")
    assert again.status_code == 400
    assert again.json() == {"detail": "Sam's account is already switched on."}


def test_a_username_can_only_be_used_once(client, db):
    log_in_coordinator(client, db)
    client.post("/api/volunteers", json={"username": "Sam"})

    response = client.post("/api/volunteers", json={"username": "SAM"})

    assert response.status_code == 409
    assert response.json()["detail"].startswith("There's already an account called SAM.")


def test_the_coordinator_gives_a_volunteer_a_new_setup_code(client, db):
    log_in_coordinator(client, db)
    sam = volunteer_with_password(db, NOW, "Sam")

    response = client.post(f"/api/volunteers/{sam.id}/setup-code")

    assert response.status_code == 201
    assert response.json()["new_account"] is False
    # Sam's old password still works until the new code is used.
    assert log_in_staff(another_browser(), "Sam").status_code == 200


# ---------- several coordinators (decided 11 November) ----------


def test_a_coordinator_makes_a_volunteer_a_coordinator_too(client, db):
    """Jordan can use the coordinator pages at once, with the same password."""
    log_in_coordinator(client, db)
    jordan = volunteer_with_password(db, NOW, "Jordan")
    jordans_phone = another_browser()
    log_in_staff(jordans_phone, "Jordan")
    assert jordans_phone.get("/api/settings").status_code == 403

    response = client.post(f"/api/volunteers/{jordan.id}/make-coordinator")

    assert response.status_code == 200
    assert (response.json()["role"], response.json()["you"]) == ("coordinator", False)
    assert jordans_phone.get("/api/settings").status_code == 200
    assert me(jordans_phone)["role"] == "coordinator"


def test_a_coordinator_made_a_volunteer_loses_the_coordinator_pages_at_once(client, db):
    """Alex hands over to Jordan, then Jordan makes Alex a volunteer."""
    log_in_coordinator(client, db)
    jordan = volunteer_with_password(db, NOW, "Jordan")
    client.post(f"/api/volunteers/{jordan.id}/make-coordinator")
    jordans_phone = another_browser()
    log_in_staff(jordans_phone, "Jordan")
    alex_id = next(row["id"] for row in jordans_phone.get("/api/volunteers").json() if row["username"] == "Alex")

    response = jordans_phone.post(f"/api/volunteers/{alex_id}/make-volunteer")

    assert response.json()["role"] == "volunteer"
    # Alex is still logged in, as a volunteer: the packing pages work, the coordinator ones don't.
    assert client.get("/api/settings").status_code == 403
    assert client.get("/api/packing").status_code == 200


def test_nobody_changes_their_own_account_on_the_staff_page(client, db):
    """So a coordinator can't switch themselves off, or leave the food bank with no coordinator."""
    log_in_coordinator(client, db)
    alex_id = client.get("/api/volunteers").json()[0]["id"]

    for action in ["make-volunteer", "switch-off", "setup-code", "switch-on"]:
        response = client.post(f"/api/volunteers/{alex_id}/{action}")
        assert response.status_code == 400
        assert response.json() == {"detail": "That's your own account. Another coordinator can change it."}
    assert client.get("/api/settings").status_code == 200


# ---------- the answers the page gets back ----------


def test_too_many_tries_says_how_long_to_wait(client, db):
    student_with_password(db, NOW)
    for _ in range(5):
        assert log_in_student(client, password="wrong guess").status_code == 401

    response = log_in_student(client)

    assert response.status_code == 429
    assert response.headers["retry-after"] == "900"
    assert response.json() == {"detail": "Too many wrong tries. Try again in 15 minutes."}


def test_a_strangers_wrong_tries_do_not_keep_the_student_waiting(client, db):
    """The student's phone logged in before, so it has a trusted-device cookie (P9)."""
    student_with_password(db, NOW)
    log_in_student(client)
    client.post("/api/logout")
    stranger = another_browser()
    for _ in range(5):
        log_in_student(stranger, password="wrong guess")
    assert log_in_student(stranger).status_code == 429

    assert log_in_student(client).status_code == 200


@pytest.mark.parametrize(
    "body, message",
    [
        ({"id_number": "2023", "password": PASSWORD}, "Enter the 9 digits on your MUN card."),
        ({"id_number": "2023 98765", "password": "x" * 129}, "A password can be at most 128 characters."),
    ],
)
def test_a_form_problem_says_what_to_fix(client, db, body, message):
    response = client.post("/api/student/login", json=body)

    assert response.status_code == 422
    [problem] = response.json()["detail"]
    assert problem["msg"] == message
    assert problem["loc"][0] == "body"


def test_a_new_password_needs_8_characters(client, db):
    issued = accounts.give_student_setup_code(db, ID_NUMBER, make_staff(db), NOW)

    response = client.post(
        "/api/student/setup", json={"id_number": ID_NUMBER, "setup_code": issued.code, "new_password": "short"}
    )

    assert response.json()["detail"][0]["msg"] == "Choose a password of at least 8 characters."


def test_answers_are_never_stored_by_the_browser(client, db):
    """A setup code on screen must be gone after Back, or after the next person sits down."""
    assert client.get("/api/me").headers["cache-control"] == "no-store"
