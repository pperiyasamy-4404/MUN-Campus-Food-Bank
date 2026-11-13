"""Each test tries to break one database rule and checks the database refuses.

The rules are the safety net under the code: they hold even if the code has a
bug, or two people press a button at the same moment. The design and the
reasons are in tables.html.
"""

import threading
from datetime import UTC, datetime, time, timedelta

import pytest
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import IntegrityError

from app.models import (
    Booking,
    BookingItem,
    BookingSubstitute,
    Category,
    CounterItem,
    Hold,
    Item,
    LoginFailure,
    LoginSession,
    PickupDay,
    PickupHours,
    Settings,
    SetupCode,
    Slot,
    Staff,
    Student,
    Tag,
    Variety,
    VarietyTag,
    WalkIn,
    WeeklyItemTotal,
    WeeklyTotal,
)
from app.security.passwords import hash_password
from tests.helpers import (
    TEST_SETTINGS,
    MONDAY,
    add,
    make_booking,
    make_day,
    make_settings,
    make_slot,
    make_staff,
    make_student,
    make_variety,
    new_hash,
    wait_until_someone_is_waiting_for_a_lock,
    refused_by,
)

NOW = datetime(2026, 11, 8, 21, 0, tzinfo=UTC)


# ---------- settings ----------


def test_sample_settings_are_allowed(db):
    make_settings(db)


def test_settings_has_only_one_row(db):
    make_settings(db)
    with refused_by(db, "ck_settings_only_one_row"):
        db.add(Settings(id=2, **TEST_SETTINGS))


@pytest.mark.parametrize(
    "changes, rule",
    [
        ({"pickup_gap_days": 0}, "ck_settings_pickup_gap_days_at_least_1"),
        ({"slot_minutes": 0}, "ck_settings_slot_minutes_at_least_1"),
        ({"slot_capacity": 0}, "ck_settings_slot_capacity_at_least_1"),
        ({"hold_minutes": 0}, "ck_settings_hold_minutes_at_least_1"),
        ({"item_limit": 0}, "ck_settings_item_limit_at_least_1"),
        ({"max_per_item": 0}, "ck_settings_max_per_item_at_least_1"),
        ({"setup_code_days": 0}, "ck_settings_setup_code_days_at_least_1"),
        ({"login_tries": 0}, "ck_settings_login_tries_at_least_1"),
        ({"login_window_minutes": 0}, "ck_settings_login_window_minutes_at_least_1"),
        ({"substitute_limit": -1}, "ck_settings_substitute_limit_not_negative"),
        (
            {"booking_opens_days_before": -1, "booking_opens_time": time(9, 0)},
            "ck_settings_booking_opens_days_before_not_negative",
        ),
        ({"max_per_item": 14}, "ck_settings_max_per_item_within_item_limit"),
        ({"retention_days": 27}, "ck_settings_retention_covers_pickup_gap"),
        (
            {"booking_opens_days_before": 0, "booking_opens_time": time(13, 0)},
            "ck_settings_booking_opens_before_it_closes",
        ),
        ({"no_show_time": time(11, 0)}, "ck_settings_no_show_after_booking_closes"),
    ],
)
def test_settings_numbers_must_make_sense(db, changes, rule):
    with refused_by(db, rule):
        db.add(Settings(**(TEST_SETTINGS | changes)))


def test_booking_can_open_on_the_pickup_day_itself(db):
    make_settings(db, booking_opens_days_before=0, booking_opens_time=time(9, 0))


# ---------- pickup hours and pickup days ----------


@pytest.mark.parametrize("weekday", [0, 8])
def test_weekday_is_1_to_7(db, weekday):
    with refused_by(db, "ck_pickup_hours_weekday_1_to_7"):
        db.add(PickupHours(weekday=weekday, starts_at=time(15, 30), ends_at=time(17, 30)))


def test_pickup_hours_end_after_they_start(db):
    with refused_by(db, "ck_pickup_hours_ends_after_it_starts"):
        db.add(PickupHours(weekday=1, starts_at=time(17, 30), ends_at=time(15, 30)))


def test_each_weekday_appears_once(db):
    add(db, PickupHours(weekday=1, starts_at=time(15, 30), ends_at=time(17, 30)))
    with refused_by(db, "pk_pickup_hours"):
        db.execute(insert(PickupHours).values(weekday=1, starts_at=time(9, 0), ends_at=time(10, 0)))


def a_day(**changes) -> PickupDay:
    """A pickup day with its times in order, except the ones changed. Each change
    below breaks exactly one rule, so the refusal can only come from that rule."""
    times = {
        "booking_opens_at": NOW,
        "booking_closes_at": NOW + timedelta(hours=19),
        "pickup_starts_at": NOW + timedelta(hours=22),
        "pickup_ends_at": NOW + timedelta(hours=24),
        "no_show_at": NOW + timedelta(hours=25),
    }
    return PickupDay(pickup_date=MONDAY, **(times | changes))


def test_a_day_with_its_times_in_order_is_allowed(db):
    add(db, a_day())


@pytest.mark.parametrize(
    "changes, rule",
    [
        ({"booking_closes_at": NOW}, "ck_pickup_days_booking_opens_before_it_closes"),
        # Packing happens between booking closing and pickup starting (K1).
        ({"pickup_starts_at": NOW + timedelta(hours=18)}, "ck_pickup_days_pickup_starts_after_booking_closes"),
        ({"pickup_ends_at": NOW + timedelta(hours=22)}, "ck_pickup_days_pickup_ends_after_it_starts"),
        # Otherwise the last slots would be no-shows before their time came.
        ({"no_show_at": NOW + timedelta(hours=23)}, "ck_pickup_days_no_show_after_pickup_ends"),
    ],
)
def test_a_days_times_come_in_order(db, changes, rule):
    with refused_by(db, rule):
        db.add(a_day(**changes))


def test_one_pickup_day_per_date(db):
    make_day(db)
    with refused_by(db, "uq_pickup_days_pickup_date"):
        make_day(db)


def test_a_closed_day_says_why(db):
    day = make_day(db)
    with refused_by(db, "ck_pickup_days_closed_has_a_reason"):
        day.closed_at = NOW


def test_a_reason_only_goes_with_a_closed_day(db):
    day = make_day(db)
    with refused_by(db, "ck_pickup_days_closed_has_a_reason"):
        day.closed_reason = "Snowstorm"


def test_closing_a_day_with_a_reason_is_allowed(db):
    day = make_day(db)
    day.closed_at = NOW
    day.closed_reason = "Snowstorm"
    db.flush()


# ---------- slots (S2) ----------


def test_slot_capacity_is_at_least_1(db):
    with refused_by(db, "ck_slots_capacity_at_least_1"):
        make_slot(db, capacity=0)


def test_slot_can_not_go_over_capacity(db):
    slot = make_slot(db, capacity=1)
    slot.booked_count = 1
    db.flush()
    with refused_by(db, "ck_slots_not_over_capacity"):
        slot.booked_count = 2


def test_capacity_can_not_be_lowered_below_the_bookings(db):
    slot = make_slot(db, capacity=2)
    slot.booked_count = 2
    db.flush()
    with refused_by(db, "ck_slots_not_over_capacity"):
        slot.capacity = 1


def test_booked_count_can_not_go_below_zero(db):
    slot = make_slot(db)
    with refused_by(db, "ck_slots_booked_count_not_negative"):
        slot.booked_count = -1


def test_no_two_slots_start_at_the_same_time_on_one_day(db):
    day = make_day(db)
    make_slot(db, day=day)
    with refused_by(db, "uq_slots_pickup_day_id_starts_at"):
        make_slot(db, day=day)


def test_two_bookings_for_the_last_place_at_the_same_moment(engine):
    """Two students press Book on the last place together. Exactly one may get it (S2).

    The first update locks the slot's row. The second waits for that lock, then
    sees the new count and is refused by the capacity rule. This test commits for
    real, on two connections, so it tidies up after itself.
    """
    with engine.begin() as connection:
        day_id = connection.execute(
            insert(PickupDay)
            .values(
                pickup_date=MONDAY + timedelta(days=700),
                booking_opens_at=NOW,
                booking_closes_at=NOW + timedelta(hours=19),
                pickup_starts_at=NOW + timedelta(hours=22),
                pickup_ends_at=NOW + timedelta(hours=24),
                no_show_at=NOW + timedelta(hours=25),
            )
            .returning(PickupDay.id)
        ).scalar_one()
        slot_id = connection.execute(
            insert(Slot).values(pickup_day_id=day_id, starts_at=NOW, capacity=1).returning(Slot.id)
        ).scalar_one()

    take_a_place = update(Slot).where(Slot.id == slot_id).values(booked_count=Slot.booked_count + 1)
    results = {}

    def ben_presses_book():
        try:
            with engine.begin() as ben:
                ben.execute(take_a_place)
            results["ben"] = "booked"
        except IntegrityError as refusal:
            results["ben"] = refusal.orig.diag.constraint_name

    try:
        with engine.begin() as ana:
            ana.execute(take_a_place)  # Ana's update locks the slot's row
            ben = threading.Thread(target=ben_presses_book)
            ben.start()
            wait_until_someone_is_waiting_for_a_lock(engine)
        # Ana's transaction has committed here, so Ben's update can go ahead.
        ben.join(timeout=10)

        assert results["ben"] == "ck_slots_not_over_capacity"
        with engine.connect() as connection:
            booked = connection.execute(text("SELECT booked_count FROM slots WHERE id = :id"), {"id": slot_id})
            assert booked.scalar_one() == 1
    finally:
        with engine.begin() as connection:
            connection.execute(delete(Slot).where(Slot.id == slot_id))
            connection.execute(delete(PickupDay).where(PickupDay.id == day_id))


# ---------- staff and students ----------


def test_staff_role_is_volunteer_or_coordinator(db):
    with refused_by(db, "ck_staff_role_is_known"):
        make_staff(db, role="admin")


def test_usernames_are_unique_ignoring_capitals(db):
    make_staff(db, username="Sam")
    with refused_by(db, "uq_staff_username_lower"):
        make_staff(db, username="sam")


def test_a_raw_id_number_can_never_be_saved(db):
    """If some code passed the ID number instead of its HMAC, the database refuses it (P2)."""
    with refused_by(db, "ck_students_id_hash_looks_like_hmac"):
        db.add(Student(id_hash="202312345", created_by_staff_id=make_staff(db).id))


def test_id_hash_is_lowercase_hex(db):
    with refused_by(db, "ck_students_id_hash_looks_like_hmac"):
        db.add(Student(id_hash=new_hash().upper(), created_by_staff_id=make_staff(db).id))


def test_one_card_one_account(db):
    """P1: the same ID hash can't have two accounts."""
    student = make_student(db)
    with refused_by(db, "uq_students_id_hash"):
        db.add(Student(id_hash=student.id_hash, created_by_staff_id=student.created_by_staff_id))


# ---------- logins ----------


def test_a_session_belongs_to_a_student_or_a_staff_member(db):
    student, staff = make_student(db), make_staff(db)
    with refused_by(db, "ck_sessions_belongs_to_one_account"):
        db.add(LoginSession(token_hash=new_hash(), student_id=student.id, staff_id=staff.id, expires_at=NOW))
    with refused_by(db, "ck_sessions_belongs_to_one_account"):
        db.add(LoginSession(token_hash=new_hash(), expires_at=NOW))


def test_a_session_stores_a_hash_not_the_ticket(db):
    with refused_by(db, "ck_sessions_token_hash_looks_like_hash"):
        db.add(LoginSession(token_hash="k3T9-x_7QmZ", student_id=make_student(db).id, expires_at=NOW))


def test_deleting_an_account_deletes_its_sessions(db):
    student = make_student(db)
    add(db, LoginSession(token_hash=new_hash(), student_id=student.id, expires_at=NOW))
    db.execute(delete(Student).where(Student.id == student.id))
    assert db.scalars(select(LoginSession)).all() == []


def test_a_setup_code_belongs_to_a_student_or_a_staff_member(db):
    staff = make_staff(db)
    with refused_by(db, "ck_setup_codes_belongs_to_one_account"):
        db.add(SetupCode(code_hash=new_hash(), issued_by_staff_id=staff.id, expires_at=NOW + timedelta(days=7)))


def test_one_setup_code_per_account(db):
    student = make_student(db)
    add(db, SetupCode(code_hash=new_hash(), student_id=student.id, issued_by_staff_id=student.created_by_staff_id, expires_at=NOW + timedelta(days=7)))
    with refused_by(db, "uq_setup_codes_student_id"):
        db.add(SetupCode(code_hash=new_hash(), student_id=student.id, issued_by_staff_id=student.created_by_staff_id, expires_at=NOW + timedelta(days=7)))


def test_a_setup_code_expires_after_it_was_issued(db):
    student = make_student(db)
    with refused_by(db, "ck_setup_codes_expires_after_issued"):
        db.add(SetupCode(code_hash=new_hash(), student_id=student.id, issued_by_staff_id=student.created_by_staff_id, issued_at=NOW, expires_at=NOW))


def test_a_setup_code_itself_can_never_be_saved(db):
    """Only its HMAC fits, so someone reading the database can't use a code first."""
    student = make_student(db)
    with refused_by(db, "ck_setup_codes_code_hash_looks_like_hmac"):
        db.add(SetupCode(code_hash="K7QM4TXP", student_id=student.id, issued_by_staff_id=student.created_by_staff_id, expires_at=NOW + timedelta(days=7)))


def test_the_setup_script_can_issue_a_code_with_no_staff_member(db):
    """The first coordinator's code comes from the setup script, not a person (R3)."""
    coordinator = make_staff(db, role="coordinator")
    add(db, SetupCode(code_hash=new_hash(), staff_id=coordinator.id, issued_by_staff_id=None, expires_at=NOW + timedelta(days=7)))


def test_a_typed_password_can_never_be_saved(db):
    """P8: only an argon2 hash fits, for students and for staff."""
    with refused_by(db, "ck_students_password_hash_is_argon2"):
        db.add(Student(id_hash=new_hash(), password_hash="hunter2hunter2", created_by_staff_id=make_staff(db).id))
    with refused_by(db, "ck_staff_password_hash_is_argon2"):
        db.add(Staff(username="pat", role="volunteer", password_hash="hunter2hunter2"))


def test_a_real_argon2_hash_is_accepted(db):
    student = make_student(db)
    student.password_hash = hash_password("a long phrase I remember")
    db.flush()


def test_wrong_password_tries_store_a_hash_not_the_number(db):
    with refused_by(db, "ck_login_failures_who_hash_looks_like_hmac"):
        db.add(LoginFailure(who_hash="202312345"))


# ---------- food ----------


def test_stock_can_not_go_below_zero(db):
    """I4: taking the last one leaves 0. Taking one more is refused."""
    variety = make_variety(db, stock=1)
    variety.stock = 0
    db.flush()
    with refused_by(db, "ck_varieties_stock_not_negative"):
        variety.stock = -1


def test_few_left_is_only_for_food_with_no_number(db):
    """With a number, students see "3 left" already (decided 12 Nov)."""
    variety = make_variety(db, stock=None)
    variety.few_left = True
    db.flush()
    with refused_by(db, "ck_varieties_few_left_only_without_a_number"):
        variety.stock = 3


def test_item_names_are_unique_ignoring_capitals(db):
    category = add(db, Category(name="Breakfast"))
    add(db, Item(name="Oats", category_id=category.id))
    with refused_by(db, "uq_items_name_lower"):
        db.add(Item(name="oats", category_id=category.id))


def test_category_and_tag_names_are_unique(db):
    add(db, Category(name="Protein"))
    with refused_by(db, "uq_categories_name_lower"):
        db.add(Category(name="PROTEIN"))
    add(db, Tag(name="Halal"))
    with refused_by(db, "uq_tags_name_lower"):
        db.add(Tag(name="halal"))


def test_variety_names_are_unique_within_an_item(db):
    variety = make_variety(db)
    with refused_by(db, "uq_varieties_item_id_name_lower"):
        db.add(Variety(item_id=variety.item_id, name=variety.name.upper()))


def test_two_items_can_have_varieties_with_the_same_name(db):
    first, second = make_variety(db), make_variety(db)
    add(db, Variety(item_id=first.item_id, name="Large"))
    add(db, Variety(item_id=second.item_id, name="Large"))


def test_a_variety_has_each_tag_once(db):
    variety = make_variety(db)
    tag = add(db, Tag(name="Vegetarian"))
    add(db, VarietyTag(variety_id=variety.id, tag_id=tag.id))
    with refused_by(db, "pk_variety_tags"):
        db.execute(insert(VarietyTag).values(variety_id=variety.id, tag_id=tag.id))


# ---------- holds (S8) ----------


def test_a_student_holds_one_slot_at_a_time(db):
    student = make_student(db)
    day = make_day(db)
    first, second = make_slot(db, day=day), make_slot(db, day=day, minutes_in=10)
    add(db, Hold(student_id=student.id, slot_id=first.id, held_until=NOW))
    with refused_by(db, "pk_holds"):
        db.execute(insert(Hold).values(student_id=student.id, slot_id=second.id, held_until=NOW))


# ---------- bookings ----------


def test_booking_status_is_one_of_five(db):
    with refused_by(db, "ck_bookings_status_is_known"):
        make_booking(db, status="lost")


def test_one_upcoming_booking_per_student(db):
    """F2, and B4: a second booking, from a double click or another tab, is refused."""
    student = make_student(db)
    make_booking(db, student=student, slot=make_slot(db, day=make_day(db, on=MONDAY)))
    thursday = make_day(db, on=MONDAY + timedelta(days=3))
    with refused_by(db, "uq_bookings_one_upcoming_per_student"):
        make_booking(db, student=student, slot=make_slot(db, day=thursday))


def test_a_new_booking_is_allowed_after_the_last_one_was_picked_up(db):
    student = make_student(db)
    volunteer = make_staff(db)
    make_booking(
        db,
        student=student,
        slot=make_slot(db, day=make_day(db, on=MONDAY)),
        status="picked_up",
        packed_at=NOW,
        packed_by_staff_id=volunteer.id,
        picked_up_at=NOW,
        picked_up_by_staff_id=volunteer.id,
    )
    make_booking(db, student=student, slot=make_slot(db, day=make_day(db, on=MONDAY + timedelta(days=28))))


def test_cancelling_and_booking_again_on_the_same_day_is_refused(db):
    """S6: otherwise cancelling and booking again would be a way to change items (I7)."""
    student = make_student(db)
    day = make_day(db)
    make_booking(
        db,
        student=student,
        slot=make_slot(db, day=day),
        status="cancelled",
        cancelled_at=NOW,
        cancel_reason="student",
    )
    with refused_by(db, "uq_bookings_student_id_pickup_day_id"):
        make_booking(db, student=student, slot=make_slot(db, day=day, minutes_in=10), code="B7Q")


def test_booking_codes_are_unique_within_a_day(db):
    day = make_day(db)
    make_booking(db, slot=make_slot(db, day=day), code="K3P")
    with refused_by(db, "uq_bookings_pickup_day_id_code"):
        make_booking(db, slot=make_slot(db, day=day, minutes_in=10), code="K3P")


def test_the_same_code_can_be_used_on_another_day(db):
    make_booking(db, slot=make_slot(db, day=make_day(db, on=MONDAY)), code="K3P")
    make_booking(db, slot=make_slot(db, day=make_day(db, on=MONDAY + timedelta(days=3))), code="K3P")


def test_a_booking_day_always_matches_its_slot(db):
    monday_slot = make_slot(db, day=make_day(db, on=MONDAY))
    thursday = make_day(db, on=MONDAY + timedelta(days=3))
    student = make_student(db)
    with refused_by(db, "fk_bookings_slot_id_pickup_day_id"):
        db.add(Booking(student_id=student.id, slot_id=monday_slot.id, pickup_day_id=thursday.id, code="K3P"))


def test_only_a_volunteer_click_counts_as_picked_up(db):
    """B3: a pickup always records which volunteer handed over the bag."""
    with refused_by(db, "ck_bookings_picked_up_by_a_volunteer"):
        make_booking(db, status="picked_up", packed_at=NOW, packed_by_staff_id=make_staff(db).id, picked_up_at=NOW)


def test_picked_up_always_has_a_time(db):
    with refused_by(db, "ck_bookings_picked_up_matches_status"):
        make_booking(db, status="picked_up", packed_at=NOW, packed_by_staff_id=make_staff(db).id)


def test_packed_always_has_a_time(db):
    with refused_by(db, "ck_bookings_packed_has_a_time"):
        make_booking(db, status="packed")


def test_a_packed_bag_always_says_who_packed_it(db):
    with refused_by(db, "ck_bookings_packed_by_a_volunteer"):
        make_booking(db, status="packed", packed_at=NOW)
    with refused_by(db, "ck_bookings_packed_by_a_volunteer"):
        make_booking(db, packed_by_staff_id=make_staff(db).id)


def test_a_cancellation_always_has_a_time_and_a_reason(db):
    with refused_by(db, "ck_bookings_cancelled_matches_status"):
        make_booking(db, status="cancelled")
    with refused_by(db, "ck_bookings_cancel_has_a_reason"):
        make_booking(db, status="cancelled", cancelled_at=NOW)
    with refused_by(db, "ck_bookings_cancel_reason_is_known"):
        make_booking(db, status="cancelled", cancelled_at=NOW, cancel_reason="bored")


def test_a_no_show_always_has_a_time(db):
    with refused_by(db, "ck_bookings_no_show_matches_status"):
        make_booking(db, status="no_show")


def test_a_booking_can_go_booked_packed_picked_up(db):
    booking = make_booking(db)
    booking.status, booking.packed_at, booking.packed_by_staff_id = "packed", NOW, make_staff(db).id
    db.flush()
    booking.status, booking.picked_up_at, booking.picked_up_by_staff_id = "picked_up", NOW, make_staff(db).id
    db.flush()


# ---------- what was booked ----------


def test_each_variety_appears_once_per_booking(db):
    booking, variety = make_booking(db), make_variety(db)
    add(db, BookingItem(booking_id=booking.id, variety_id=variety.id))
    with refused_by(db, "pk_booking_items"):
        db.execute(insert(BookingItem).values(booking_id=booking.id, variety_id=variety.id))


def test_quantity_is_at_least_1(db):
    with refused_by(db, "ck_booking_items_quantity_at_least_1"):
        db.add(BookingItem(booking_id=make_booking(db).id, variety_id=make_variety(db).id, quantity=0))


def test_substitute_ranks_start_from_1(db):
    with refused_by(db, "ck_booking_substitutes_rank_from_1"):
        db.add(BookingSubstitute(booking_id=make_booking(db).id, rank=0, variety_id=make_variety(db).id))


def test_each_substitute_rank_appears_once(db):
    booking = make_booking(db)
    add(db, BookingSubstitute(booking_id=booking.id, rank=1, variety_id=make_variety(db).id))
    with refused_by(db, "pk_booking_substitutes"):
        db.execute(insert(BookingSubstitute).values(booking_id=booking.id, rank=1, variety_id=make_variety(db).id))


def test_a_variety_is_listed_as_a_substitute_once(db):
    booking, variety = make_booking(db), make_variety(db)
    add(db, BookingSubstitute(booking_id=booking.id, rank=1, variety_id=variety.id))
    with refused_by(db, "uq_booking_substitutes_booking_id_variety_id"):
        db.add(BookingSubstitute(booking_id=booking.id, rank=2, variety_id=variety.id))


# ---------- packing (step 6) ----------


def test_missing_is_never_more_than_was_booked(db):
    booking, variety = make_booking(db), make_variety(db)
    line = add(db, BookingItem(booking_id=booking.id, variety_id=variety.id, quantity=2))
    line.missing = 2
    db.flush()
    with refused_by(db, "ck_booking_items_missing_within_quantity"):
        line.missing = 3
    with refused_by(db, "ck_booking_items_missing_within_quantity"):
        line.missing = -1


def test_a_substitute_can_only_replace_food_booked_in_the_same_booking(db):
    """U5: a swap always points at something this student booked."""
    booking = make_booking(db)
    other_booking = make_booking(db, slot=make_slot(db, day=make_day(db, on=MONDAY + timedelta(days=3))))
    oil, rice = make_variety(db), make_variety(db)
    add(db, BookingItem(booking_id=booking.id, variety_id=oil.id))
    add(db, BookingItem(booking_id=other_booking.id, variety_id=rice.id))
    substitute = add(db, BookingSubstitute(booking_id=booking.id, rank=1, variety_id=make_variety(db).id))

    substitute.replaces_variety_id = oil.id
    db.flush()
    with refused_by(db, "fk_booking_substitutes_booking_id_replaces_variety_id"):
        substitute.replaces_variety_id = rice.id


def test_deleting_a_packed_booking_deletes_its_food_and_swaps(db):
    """The retention job (step 8) deletes old bookings. Their swaps must go with them."""
    booking, oil = make_booking(db), make_variety(db)
    add(db, BookingItem(booking_id=booking.id, variety_id=oil.id, missing=1))
    add(db, BookingSubstitute(booking_id=booking.id, rank=1, variety_id=make_variety(db).id, replaces_variety_id=oil.id))

    db.execute(delete(Booking).where(Booking.id == booking.id))

    assert db.scalars(select(BookingSubstitute).where(BookingSubstitute.booking_id == booking.id)).all() == []


# ---------- the counter (step 7) ----------


def _extra(db, item_name: str = "Bread") -> Variety:
    category = add(db, Category(name=f"Bakery {item_name}"))
    item = add(db, Item(name=item_name, category_id=category.id, is_extra=True))
    return add(db, Variety(item_id=item.id, name=f"White {item_name.lower()}", stock=5))


def _counter_item(variety: Variety, item: Item | None = None, **columns) -> CounterItem:
    item_id = item.id if item else variety.item_id
    is_extra = columns.pop("is_extra", None)
    return CounterItem(variety_id=variety.id, item_id=item_id, is_extra=is_extra, **columns)


def test_a_counter_item_belongs_to_one_booking_or_one_walk_in(db):
    booking, variety = make_booking(db), make_variety(db)
    walk_in = add(db, WalkIn(student_id=make_student(db).id, pickup_day_id=booking.pickup_day_id, served_at=NOW, served_by_staff_id=make_staff(db).id))
    with refused_by(db, "ck_counter_items_for_one_pickup"):
        db.add(_counter_item(variety, is_extra=False))
    with refused_by(db, "ck_counter_items_for_one_pickup"):
        db.add(_counter_item(variety, is_extra=False, booking_id=booking.id, walk_in_id=walk_in.id))


def test_one_of_each_extra_item_per_pickup(db):
    """E3: one bread, even if there are two kinds of bread."""
    booking, white = make_booking(db), _extra(db)
    brown = add(db, Variety(item_id=white.item_id, name="Brown bread", stock=5))
    add(db, _counter_item(white, is_extra=True, booking_id=booking.id))
    with refused_by(db, "uq_counter_items_one_extra_per_item_per_booking"):
        db.add(_counter_item(brown, is_extra=True, booking_id=booking.id))


def test_one_of_each_extra_item_per_walk_in(db):
    day, white = make_day(db), _extra(db)
    brown = add(db, Variety(item_id=white.item_id, name="Brown bread", stock=5))
    walk_in = add(db, WalkIn(student_id=make_student(db).id, pickup_day_id=day.id, served_at=NOW, served_by_staff_id=make_staff(db).id))
    add(db, _counter_item(white, is_extra=True, walk_in_id=walk_in.id))
    with refused_by(db, "uq_counter_items_one_extra_per_item_per_walk_in"):
        db.add(_counter_item(brown, is_extra=True, walk_in_id=walk_in.id))


def test_an_extra_is_one(db):
    with refused_by(db, "ck_counter_items_one_of_an_extra"):
        db.add(_counter_item(_extra(db), is_extra=True, booking_id=make_booking(db).id, quantity=2))


def test_the_copied_item_and_is_extra_must_be_right(db):
    """The two links keep the copies honest, so the extra rule above can't be dodged."""
    booking, bread, oats = make_booking(db), _extra(db), make_variety(db)
    with refused_by(db, "fk_counter_items_item_id_is_extra"):
        db.add(_counter_item(bread, is_extra=False, booking_id=booking.id))
    with refused_by(db, "fk_counter_items_variety_id_item_id"):
        db.add(_counter_item(bread, item=db.get(Item, oats.item_id), is_extra=False, booking_id=booking.id))


def test_one_walk_in_per_student_per_day(db):
    day, student, staff = make_day(db), make_student(db), make_staff(db)
    add(db, WalkIn(student_id=student.id, pickup_day_id=day.id, served_at=NOW, served_by_staff_id=staff.id))
    with refused_by(db, "uq_walk_ins_student_id_pickup_day_id"):
        db.add(WalkIn(student_id=student.id, pickup_day_id=day.id, served_at=NOW, served_by_staff_id=staff.id))


# ---------- weekly totals (P7) ----------


def _week(**changes) -> WeeklyTotal:
    counts = {"picked_up": 0, "walk_ins": 0, "no_shows": 0, "cancelled": 0}
    return WeeklyTotal(**({"week_starts_on": MONDAY} | counts | changes))


def test_a_week_starts_on_a_monday(db):
    add(db, _week())
    with refused_by(db, "ck_weekly_totals_week_starts_on_a_monday"):
        db.add(_week(week_starts_on=MONDAY + timedelta(days=1)))


@pytest.mark.parametrize("count", ["picked_up", "walk_ins", "no_shows", "cancelled"])
def test_a_weeks_counts_are_never_negative(db, count):
    with refused_by(db, f"ck_weekly_totals_{count}_not_negative"):
        db.add(_week(**{count: -1}))


def test_an_items_weekly_total_is_at_least_1_and_belongs_to_a_week(db):
    item_id = make_variety(db).item_id
    with refused_by(db, "fk_weekly_item_totals_week_starts_on"):
        db.add(WeeklyItemTotal(week_starts_on=MONDAY, item_id=item_id, given_out=1))
    add(db, _week())
    with refused_by(db, "ck_weekly_item_totals_given_out_at_least_1"):
        db.add(WeeklyItemTotal(week_starts_on=MONDAY, item_id=item_id, given_out=0))
