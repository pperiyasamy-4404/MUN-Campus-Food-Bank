"""The account rules, checked straight from app/services/accounts.py, with no web addresses.

Setup codes (R1, R3), passwords (P6, P8), slowing down wrong tries (P9), and
the audit log (R4). The web side is in test_login_api.py.
"""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AuditLog, LoginFailure, LoginSession, Settings, SetupCode, Staff, Student
from app.sample_data import SAMPLE_SETTINGS
from app.security.keyed_hash import id_hash, username_hash
from app.security.passwords import password_matches
from app.security.sessions import start_session
from app.security.setup_codes import ALPHABET, setup_code_hash
from app.security.wrong_tries import device_cookie_for
from app.services import accounts
from app.services.accounts import (
    WRONG_STAFF_PASSWORD,
    WRONG_STUDENT_CODE,
    WRONG_STUDENT_PASSWORD,
    AccountProblem,
    NameTaken,
    NotFound,
    TooManyTries,
    WrongDetails,
)
from tests.helpers import (
    ID_NUMBER,
    OTHER_ID_NUMBER,
    PASSWORD,
    coordinator,
    make_staff,
    student_with_password,
    volunteer_with_password,
)

NOW = datetime(2026, 11, 8, 21, 0, tzinfo=UTC)
WRONG = "not my password at all"


def log_actions(db) -> list[tuple[str, int | None, int | None, int | None]]:
    """The audit log, as (action, by, student, staff it was done to)."""
    rows = db.execute(
        select(AuditLog.action, AuditLog.staff_id, AuditLog.student_id, AuditLog.affected_staff_id).order_by(AuditLog.id)
    )
    return [tuple(row) for row in rows]


def code_of(db, student: Student) -> SetupCode | None:
    return db.scalar(select(SetupCode).where(SetupCode.student_id == student.id))


def student_has_password(db, id_number: str, password: str, now: datetime = NOW) -> bool:
    try:
        accounts.log_in_student(db, id_number, password, None, now)
    except WrongDetails:
        return False
    return True


# ---------- at the counter (R1) ----------


def test_a_new_card_gets_an_account_and_a_setup_code(db_with_settings):
    db = db_with_settings
    volunteer = make_staff(db, "Sam")

    issued = accounts.give_student_setup_code(db, ID_NUMBER, volunteer, NOW)

    student = db.scalar(select(Student))
    assert issued.new_account
    assert student.id_hash == id_hash(ID_NUMBER)
    assert student.password_hash is None
    assert student.created_by_staff_id == volunteer.id
    # Like K7QM-4TXP, with no 0/O or 1/I/L to misread.
    first, second = issued.code.split("-")
    assert len(first) == len(second) == 4
    assert set(first + second) <= set(ALPHABET)
    # Only the code's HMAC is saved, and it runs out in 7 days (the sample setting).
    saved = code_of(db, student)
    assert saved.code_hash == setup_code_hash(issued.code)
    assert issued.expires_at == saved.expires_at == NOW + timedelta(days=7)
    # R4: who made the account and who gave the code.
    assert log_actions(db) == [
        ("created_student", volunteer.id, student.id, None),
        ("issued_setup_code", volunteer.id, student.id, None),
    ]


def test_the_student_chooses_a_password_with_their_code(db_with_settings):
    db = db_with_settings
    issued = accounts.give_student_setup_code(db, ID_NUMBER, make_staff(db), NOW)

    student = accounts.set_student_password(db, ID_NUMBER, issued.code, PASSWORD, None, NOW)

    # P8: stored only as an argon2 hash.
    assert student.password_hash.startswith("$argon2id$")
    assert PASSWORD not in student.password_hash
    assert student_has_password(db, ID_NUMBER, PASSWORD)
    # The first password is not a reset, so the student isn't told about one (R4).
    assert student.password_reset_at is None


def test_a_setup_code_works_once(db_with_settings):
    db = db_with_settings
    issued = accounts.give_student_setup_code(db, ID_NUMBER, make_staff(db), NOW)
    accounts.set_student_password(db, ID_NUMBER, issued.code, PASSWORD, None, NOW)

    with pytest.raises(WrongDetails):
        accounts.set_student_password(db, ID_NUMBER, issued.code, "someone else's choice", None, NOW)
    assert student_has_password(db, ID_NUMBER, PASSWORD)


def test_a_setup_code_runs_out_after_the_setup_code_lifetime(db_with_settings):
    db = db_with_settings
    staff = make_staff(db)
    issued = accounts.give_student_setup_code(db, ID_NUMBER, staff, NOW)

    with pytest.raises(WrongDetails) as refusal:
        accounts.set_student_password(db, ID_NUMBER, issued.code, PASSWORD, None, NOW + timedelta(days=7))
    assert refusal.value.message == WRONG_STUDENT_CODE

    # A second before, it still works.
    issued = accounts.give_student_setup_code(db, ID_NUMBER, staff, NOW)
    accounts.set_student_password(db, ID_NUMBER, issued.code, PASSWORD, None, NOW + timedelta(days=7, seconds=-1))


def test_a_code_only_works_with_the_card_it_was_given_for(db_with_settings):
    db = db_with_settings
    staff = make_staff(db)
    issued = accounts.give_student_setup_code(db, ID_NUMBER, staff, NOW)
    accounts.give_student_setup_code(db, OTHER_ID_NUMBER, staff, NOW)

    with pytest.raises(WrongDetails):
        accounts.set_student_password(db, OTHER_ID_NUMBER, issued.code, PASSWORD, None, NOW)


def test_a_new_code_replaces_the_old_one(db_with_settings):
    db = db_with_settings
    staff = make_staff(db)
    first = accounts.give_student_setup_code(db, ID_NUMBER, staff, NOW)

    second = accounts.give_student_setup_code(db, ID_NUMBER, staff, NOW)

    assert not second.new_account
    assert len(db.scalars(select(SetupCode)).all()) == 1
    with pytest.raises(WrongDetails):
        accounts.set_student_password(db, ID_NUMBER, first.code, PASSWORD, None, NOW)
    accounts.set_student_password(db, ID_NUMBER, second.code, PASSWORD, None, NOW)


def test_a_forgotten_password_is_reset_with_a_new_code(db_with_settings):
    """R1, R4: the old password works until the new code is used, then the student
    is logged out everywhere and sees "password reset on DATE"."""
    db = db_with_settings
    student = student_with_password(db, NOW)
    start_session(db, student, NOW)  # logged in on a flatmate's laptop
    later = NOW + timedelta(days=3)

    issued = accounts.give_student_setup_code(db, ID_NUMBER, make_staff(db), later)

    # A code given by mistake locks nobody out.
    assert student_has_password(db, ID_NUMBER, PASSWORD, later)
    assert student.password_reset_at is None

    accounts.set_student_password(db, ID_NUMBER, issued.code, "a brand new phrase", None, later)

    assert not student_has_password(db, ID_NUMBER, PASSWORD, later)
    assert student_has_password(db, ID_NUMBER, "a brand new phrase", later)
    assert student.password_reset_at == later
    assert db.scalars(select(LoginSession).where(LoginSession.student_id == student.id)).all() == []


def test_the_password_can_not_be_the_id_number(db_with_settings):
    db = db_with_settings
    issued = accounts.give_student_setup_code(db, ID_NUMBER, make_staff(db), NOW)

    with pytest.raises(AccountProblem, match="isn't your ID number"):
        accounts.set_student_password(db, ID_NUMBER, issued.code, ID_NUMBER, None, NOW)


# ---------- logging in (P6, P9) ----------


@pytest.mark.parametrize(
    "case",
    ["no account", "no password chosen yet", "wrong password"],
)
def test_every_wrong_login_gets_the_same_words(db_with_settings, case):
    """So the answer never tells anyone whether a number has an account (P9)."""
    db = db_with_settings
    if case == "no password chosen yet":
        accounts.give_student_setup_code(db, ID_NUMBER, make_staff(db), NOW)
    if case == "wrong password":
        student_with_password(db, NOW)
    password = PASSWORD if case != "wrong password" else WRONG

    with pytest.raises(WrongDetails) as refusal:
        accounts.log_in_student(db, ID_NUMBER, password, None, NOW)

    assert refusal.value.message == WRONG_STUDENT_PASSWORD
    assert refusal.value.status_code == 401


def try_wrong_passwords(db, times: int, id_number: str = ID_NUMBER, now: datetime = NOW, device: str | None = None):
    for _ in range(times):
        with pytest.raises(WrongDetails):
            accounts.log_in_student(db, id_number, WRONG, device, now)


def test_after_5_wrong_tries_even_the_right_password_has_to_wait(db_with_settings):
    """P9: the password isn't even checked, so guessing gets no faster."""
    db = db_with_settings
    student_with_password(db, NOW)
    try_wrong_passwords(db, 5)

    with pytest.raises(TooManyTries) as refusal:
        accounts.log_in_student(db, ID_NUMBER, PASSWORD, None, NOW + timedelta(minutes=1))

    assert refusal.value.status_code == 429
    assert refusal.value.retry_after_seconds == 14 * 60
    assert refusal.value.message == "Too many wrong tries. Try again in 14 minutes."
    # Waiting doesn't add more wrong tries.
    assert len(db.scalars(select(LoginFailure)).all()) == 5


def test_a_try_is_allowed_again_15_minutes_after_the_oldest_one(db_with_settings):
    """Slowed down, never locked: nobody has to unlock the account."""
    db = db_with_settings
    student_with_password(db, NOW)
    try_wrong_passwords(db, 5)

    with pytest.raises(TooManyTries):
        accounts.log_in_student(db, ID_NUMBER, PASSWORD, None, NOW + timedelta(minutes=15, seconds=-1))
    accounts.log_in_student(db, ID_NUMBER, PASSWORD, None, NOW + timedelta(minutes=15))


def test_logging_in_forgets_the_earlier_slips(db_with_settings):
    db = db_with_settings
    student_with_password(db, NOW)
    try_wrong_passwords(db, 4)

    accounts.log_in_student(db, ID_NUMBER, PASSWORD, None, NOW)

    try_wrong_passwords(db, 4)  # 4 more slips, and still not made to wait
    accounts.log_in_student(db, ID_NUMBER, PASSWORD, None, NOW)


def test_numbers_with_no_account_are_slowed_down_too(db_with_settings):
    """Otherwise someone could tell which numbers have accounts from which ones say "wait"."""
    db = db_with_settings
    try_wrong_passwords(db, 5)

    with pytest.raises(TooManyTries):
        accounts.log_in_student(db, ID_NUMBER, WRONG, None, NOW)


def test_wrong_setup_codes_count_as_wrong_tries(db_with_settings):
    """Or a guesser would try codes instead of passwords."""
    db = db_with_settings
    issued = accounts.give_student_setup_code(db, ID_NUMBER, make_staff(db), NOW)
    for _ in range(5):
        with pytest.raises(WrongDetails):
            accounts.set_student_password(db, ID_NUMBER, "AAAA-AAAA", PASSWORD, None, NOW)

    with pytest.raises(TooManyTries):
        accounts.set_student_password(db, ID_NUMBER, issued.code, PASSWORD, None, NOW)


def test_one_numbers_wrong_tries_do_not_slow_down_another(db_with_settings):
    db = db_with_settings
    student_with_password(db, NOW)
    try_wrong_passwords(db, 5, id_number=OTHER_ID_NUMBER)

    accounts.log_in_student(db, ID_NUMBER, PASSWORD, None, NOW)


def test_someone_elses_wrong_tries_do_not_slow_down_the_students_own_phone(db_with_settings):
    """The trusted-device cookie: the student's phone has logged in before, so its
    tries are counted on their own. A stranger who knows the number can't keep
    the student waiting on booking night."""
    db = db_with_settings
    student_with_password(db, NOW)
    phone = device_cookie_for(id_hash(ID_NUMBER))
    try_wrong_passwords(db, 5)  # the stranger, with no device cookie

    accounts.log_in_student(db, ID_NUMBER, PASSWORD, phone, NOW)


def test_a_trusted_device_is_still_limited_to_5_tries(db_with_settings):
    db = db_with_settings
    student_with_password(db, NOW)
    phone = device_cookie_for(id_hash(ID_NUMBER))
    try_wrong_passwords(db, 5, device=phone)

    with pytest.raises(TooManyTries):
        accounts.log_in_student(db, ID_NUMBER, PASSWORD, phone, NOW)
    # ...and that doesn't slow down anyone else.
    accounts.log_in_student(db, ID_NUMBER, PASSWORD, None, NOW)


@pytest.mark.parametrize(
    "cookie",
    [
        "made-up-token.made-up-signature",
        "no-dot-at-all",
        # A real cookie, but for a different account.
        device_cookie_for(id_hash(OTHER_ID_NUMBER)),
    ],
)
def test_a_made_up_device_cookie_counts_as_no_cookie(db_with_settings, cookie):
    """Only the server can sign one, so a guesser can't make their own to skip the limit."""
    db = db_with_settings
    student_with_password(db, NOW)
    try_wrong_passwords(db, 5)

    with pytest.raises(TooManyTries):
        accounts.log_in_student(db, ID_NUMBER, PASSWORD, cookie, NOW)


# ---------- staff (R3) ----------


def test_the_coordinator_adds_a_volunteer_who_chooses_their_own_password(db_with_settings):
    db = db_with_settings
    alex = coordinator(db)

    volunteer, issued = accounts.add_volunteer(db, "Sam", alex, NOW)

    assert (volunteer.role, volunteer.created_by_staff_id, volunteer.password_hash) == ("volunteer", alex.id, None)
    assert issued.new_account
    accounts.set_staff_password(db, "Sam", issued.code, PASSWORD, None, NOW)
    assert password_matches(volunteer.password_hash, PASSWORD)
    assert log_actions(db) == [
        ("created_volunteer", alex.id, None, volunteer.id),
        ("issued_setup_code", alex.id, None, volunteer.id),
    ]


def test_capitals_do_not_matter_in_a_username(db_with_settings):
    db = db_with_settings
    sam = volunteer_with_password(db, NOW, "Sam")

    assert accounts.log_in_staff(db, "SAM", PASSWORD, None, NOW) is sam
    with pytest.raises(NameTaken):
        accounts.add_volunteer(db, "sam", coordinator(db), NOW)


def test_a_wrong_staff_password_gets_the_same_words_as_a_wrong_username(db_with_settings):
    db = db_with_settings
    volunteer_with_password(db, NOW, "Sam")

    for username, password in [("Sam", WRONG), ("Nobody", PASSWORD)]:
        with pytest.raises(WrongDetails) as refusal:
            accounts.log_in_staff(db, username, password, None, NOW)
        assert refusal.value.message == WRONG_STAFF_PASSWORD


def test_staff_wrong_tries_are_counted_per_username(db_with_settings):
    db = db_with_settings
    volunteer_with_password(db, NOW, "Sam")
    for _ in range(5):
        with pytest.raises(WrongDetails):
            accounts.log_in_staff(db, "sam", WRONG, None, NOW)

    with pytest.raises(TooManyTries):
        accounts.log_in_staff(db, "Sam", PASSWORD, None, NOW)
    saved = db.scalars(select(LoginFailure.who_hash)).all()
    assert set(saved) == {username_hash("Sam")}


def test_a_staff_password_can_not_be_the_username(db_with_settings):
    db = db_with_settings
    _, issued = accounts.add_volunteer(db, "Samantha", coordinator(db), NOW)

    with pytest.raises(AccountProblem, match="isn't your username"):
        accounts.set_staff_password(db, "Samantha", issued.code, "SAMANTHA", None, NOW)


def test_a_switched_off_volunteer_can_not_log_in_or_use_a_code(db_with_settings):
    """Logged out everywhere at once, but the account is kept for the log (R4)."""
    db = db_with_settings
    alex = coordinator(db)
    sam = volunteer_with_password(db, NOW, "Sam")
    start_session(db, sam, NOW)
    accounts.give_volunteer_setup_code(db, sam, alex, NOW)
    later = NOW + timedelta(hours=1)

    accounts.switch_off_volunteer(db, sam, alex, later)

    assert sam.disabled_at == later
    assert db.scalars(select(LoginSession).where(LoginSession.staff_id == sam.id)).all() == []
    assert db.scalars(select(SetupCode).where(SetupCode.staff_id == sam.id)).all() == []
    with pytest.raises(WrongDetails) as refusal:
        accounts.log_in_staff(db, "Sam", PASSWORD, None, later)
    assert refusal.value.message == WRONG_STAFF_PASSWORD
    with pytest.raises(AccountProblem, match="switched off"):
        accounts.give_volunteer_setup_code(db, sam, alex, later)
    assert db.get(Staff, sam.id) is not None
    assert log_actions(db)[-1] == ("switched_off_volunteer", alex.id, None, sam.id)


def test_switching_off_twice_changes_nothing_more(db_with_settings):
    db = db_with_settings
    alex = coordinator(db)
    sam = volunteer_with_password(db, NOW, "Sam")
    accounts.switch_off_volunteer(db, sam, alex, NOW)

    accounts.switch_off_volunteer(db, sam, alex, NOW + timedelta(days=1))

    assert sam.disabled_at == NOW
    assert [row[0] for row in log_actions(db)].count("switched_off_volunteer") == 1


def test_the_coordinator_account_is_not_in_the_volunteer_list(db_with_settings):
    """The coordinator can't switch off their own account by mistake."""
    db = db_with_settings
    alex = coordinator(db)

    for staff_id in [alex.id, 999_999]:
        with pytest.raises(NotFound):
            accounts.volunteer_with_id(db, staff_id)


# ---------- the setup script (R3) ----------


def test_the_setup_script_makes_the_first_coordinator(db_with_settings):
    db = db_with_settings

    issued = accounts.set_up_first_coordinator(db, "Alex", NOW)

    alex = db.scalar(select(Staff))
    assert (alex.username, alex.role, alex.created_by_staff_id) == ("Alex", "coordinator", None)
    assert issued.new_account
    # Nobody gave the code: the script did.
    assert db.scalar(select(SetupCode)).issued_by_staff_id is None
    assert log_actions(db) == [
        ("created_coordinator", None, None, alex.id),
        ("issued_setup_code", None, None, alex.id),
    ]
    accounts.set_staff_password(db, "alex", issued.code, PASSWORD, None, NOW)
    assert accounts.log_in_staff(db, "Alex", PASSWORD, None, NOW) is alex


def test_running_the_setup_script_again_gives_a_new_code(db_with_settings):
    """For a coordinator who forgot their password."""
    db = db_with_settings
    first = accounts.set_up_first_coordinator(db, "Alex", NOW)

    second = accounts.set_up_first_coordinator(db, "ALEX", NOW)

    assert not second.new_account
    assert second.code != first.code
    assert len(db.scalars(select(Staff)).all()) == 1


def test_the_setup_script_never_makes_a_second_coordinator(db_with_settings):
    db = db_with_settings
    accounts.set_up_first_coordinator(db, "Alex", NOW)

    with pytest.raises(AccountProblem, match="already set up: Alex"):
        accounts.set_up_first_coordinator(db, "Jordan", NOW)


def test_the_setup_script_does_not_turn_a_volunteer_into_the_coordinator(db_with_settings):
    db = db_with_settings
    accounts.set_up_first_coordinator(db, "Alex", NOW)
    make_staff(db, "Sam")

    with pytest.raises(AccountProblem, match="is a volunteer"):
        accounts.set_up_first_coordinator(db, "Sam", NOW)


# ---------- at the same moment ----------


def test_ten_wrong_tries_at_the_same_moment_still_get_only_5_checks(engine):
    """Without the lock in wait_until, all 10 would count 0 earlier tries and all be checked.

    Each try has its own connection, like 10 phones, and commits for real, so
    the test tidies up after itself.
    """
    with Session(engine) as db:
        db.add(Settings(**SAMPLE_SETTINGS))
        db.commit()
    start_together = threading.Barrier(10)
    answers = []

    def one_phone():
        with Session(engine) as db:
            start_together.wait()
            try:
                accounts.log_in_student(db, ID_NUMBER, WRONG, None, NOW)
            except (WrongDetails, TooManyTries) as answer:
                answers.append(type(answer))

    try:
        phones = [threading.Thread(target=one_phone) for _ in range(10)]
        for phone in phones:
            phone.start()
        for phone in phones:
            phone.join()
        assert sorted(answer.__name__ for answer in answers) == ["TooManyTries"] * 5 + ["WrongDetails"] * 5
    finally:
        with Session(engine) as db:
            db.execute(delete(LoginFailure))
            db.execute(delete(Settings))
            db.commit()
