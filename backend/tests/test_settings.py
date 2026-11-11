"""The Settings page: the food bank's numbers and the weekly pickup hours (R3).

The rules between settings are checked straight from app/services/settings.py,
then the page's addresses the way the page uses them.
"""

from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy import select

from app.models import AuditLog, PickupDay, PickupHours, Settings, Slot
from app.problems import Problem
from app.sample_data import SAMPLE_SETTINGS
from app.services import settings as rules
from app.services.pickup_days import make_pickup_day
from app.services.settings import WeeklyHours
from tests.helpers import MONDAY, THURSDAY, coordinator, log_in, make_staff, stop_the_clock_at

NOW = datetime(2026, 11, 8, 19, 30, tzinfo=UTC)  # Sunday 4 pm
SAMPLE_HOURS = [WeeklyHours(1, time(15, 30), time(17, 30)), WeeklyHours(4, time(15, 30), time(17, 30))]


def why_not(hours=SAMPLE_HOURS, **changes) -> str | None:
    return rules.why_not_fit(SAMPLE_SETTINGS | changes, hours)


# ---------- the rules between settings ----------


def test_the_sample_settings_fit_together():
    assert why_not() is None


def test_the_limits_fit_together():
    assert why_not(max_per_item=14) == "The most of one item can't be more than the item limit."
    assert why_not(retention_days=27) == (
        "Booking details have to be kept at least as long as the pickup gap. "
        "Otherwise a pickup could be deleted while it still counts."
    )


def test_booking_opens_before_it_closes_and_after_the_day_is_made():
    assert why_not(booking_opens_days_before=0, booking_opens_time=time(12, 0)) == (
        "Booking opens and closes on the same day, so it has to open before it closes."
    )
    assert why_not(booking_opens_days_before=0, booking_opens_time=time(8, 0)) is None
    assert why_not(booking_opens_days_before=7) == (
        "Booking can open at most 6 days before, because days are made a week ahead."
    )
    assert why_not(booking_opens_days_before=6) is None


def test_every_pickup_day_fits_between_booking_closing_and_no_shows():
    assert why_not(booking_closes_time=time(16, 0)) == (
        "Monday: booking closes at 4:00 p.m., after pickup starts at 3:30 p.m. "
        "It has to close first, so the bags can be packed."
    )
    late_thursday = [SAMPLE_HOURS[0], WeeklyHours(4, time(16, 0), time(18, 30))]
    assert why_not(late_thursday) == (
        "Thursday: pickup ends at 6:30 p.m., after the no-show time, 6:00 p.m. "
        "No-shows have to come after pickup ends."
    )


def test_pickup_hours_make_sense_on_their_own():
    assert why_not([WeeklyHours(1, time(17, 30), time(15, 30))]) == "Monday: pickup has to end after it starts."
    assert why_not([WeeklyHours(1, time(15, 30), time(15, 35))]) == (
        "Monday: the pickup hours are shorter than one 10-minute slot."
    )
    assert why_not([]) == (
        "Choose at least one pickup day of the week. To stop for a while, close the days instead."
    )
    assert why_not([SAMPLE_HOURS[0], SAMPLE_HOURS[0]]) == "Each day of the week can have one set of pickup hours."


# ---------- saving ----------


def test_saving_changes_the_settings_and_the_weekly_hours_and_logs_it(db_with_sample_week):
    db = db_with_sample_week
    alex = coordinator(db)
    friday = WeeklyHours(5, time(13, 0), time(15, 0))

    rules.change_settings(db, SAMPLE_SETTINGS | {"slot_capacity": 2}, [SAMPLE_HOURS[0], friday], alex, NOW)

    assert rules.food_bank_settings(db).slot_capacity == 2
    assert rules.weekly_hours(db) == [SAMPLE_HOURS[0], friday]
    line = db.scalar(select(AuditLog).where(AuditLog.action == "changed_settings"))
    assert (line.staff_id, line.at) == (alex.id, NOW)


def test_settings_that_dont_fit_are_not_saved(db_with_sample_week):
    db = db_with_sample_week

    with pytest.raises(Problem):
        rules.change_settings(db, SAMPLE_SETTINGS | {"max_per_item": 20}, SAMPLE_HOURS, coordinator(db), NOW)

    assert rules.food_bank_settings(db).max_per_item == 1


def test_days_already_made_keep_their_times_and_new_days_use_the_new_ones(db_with_sample_week):
    db = db_with_sample_week
    monday = make_pickup_day(db, MONDAY)
    later_hours = [WeeklyHours(1, time(16, 0), time(18, 0))]

    rules.change_settings(
        db, SAMPLE_SETTINGS | {"no_show_time": time(18, 30), "slot_minutes": 15}, later_hours, coordinator(db), NOW
    )

    assert monday.pickup_starts_at == datetime(2026, 11, 9, 19, 0, tzinfo=UTC)  # still 3:30 pm
    next_monday = make_pickup_day(db, date(2026, 11, 16))
    assert next_monday.pickup_starts_at == datetime(2026, 11, 16, 19, 30, tzinfo=UTC)  # 4:00 pm
    assert next_monday.no_show_at == datetime(2026, 11, 16, 22, 0, tzinfo=UTC)  # 6:30 pm


# ---------- students per slot reaches days not open yet (the user's answer, 10 Nov) ----------


def capacities(db, day: PickupDay) -> set[int]:
    return set(db.scalars(select(Slot.capacity).where(Slot.pickup_day_id == day.id).execution_options(populate_existing=True)))


def test_students_per_slot_reaches_days_whose_booking_hasnt_opened(db_with_sample_week):
    db = db_with_sample_week
    monday, thursday = make_pickup_day(db, MONDAY), make_pickup_day(db, THURSDAY)
    # Booking for Monday opened at 3 pm on Sunday, an hour before NOW. Thursday's opens on Wednesday.
    monday.booking_opens_at = datetime(2026, 11, 8, 18, 30, tzinfo=UTC)
    db.flush()

    changed = rules.change_settings(db, SAMPLE_SETTINGS | {"slot_capacity": 2}, SAMPLE_HOURS, coordinator(db), NOW)

    assert changed == [THURSDAY]
    assert capacities(db, thursday) == {2}
    # Students may be booking Monday right now, so it stays as it was.
    assert capacities(db, monday) == {1}


def test_a_slot_never_gets_fewer_places_than_are_booked(db_with_sample_week):
    """A day whose opening was moved later after students booked it (S9)."""
    db = db_with_sample_week
    db.execute(Settings.__table__.update().values(slot_capacity=3))
    monday = make_pickup_day(db, MONDAY)
    first = db.scalars(select(Slot).where(Slot.pickup_day_id == monday.id).order_by(Slot.starts_at)).first()
    first.booked_count = 2
    db.flush()

    rules.change_settings(db, SAMPLE_SETTINGS | {"slot_capacity": 1}, SAMPLE_HOURS, coordinator(db), NOW)

    assert db.scalar(select(Slot.capacity).where(Slot.id == first.id).execution_options(populate_existing=True)) == 2
    assert capacities(db, monday) == {1, 2}


def test_other_settings_never_change_days_already_made(db_with_sample_week):
    db = db_with_sample_week
    monday = make_pickup_day(db, MONDAY)

    changed = rules.change_settings(db, SAMPLE_SETTINGS | {"item_limit": 10}, SAMPLE_HOURS, coordinator(db), NOW)

    assert changed == []
    assert capacities(db, monday) == {1}


# ---------- the page's addresses ----------


def as_sent(**changes) -> dict:
    """The sample settings the way the page sends them: times as "17:00"."""
    sent = {name: f"{value:%H:%M}" if isinstance(value, time) else value for name, value in SAMPLE_SETTINGS.items()}
    sent["pickup_hours"] = [
        {"weekday": 1, "starts_at": "15:30", "ends_at": "17:30"},
        {"weekday": 4, "starts_at": "15:30", "ends_at": "17:30"},
    ]
    return sent | changes


@pytest.fixture
def alex_logged_in(client, db_with_sample_week):
    db = db_with_sample_week
    alex = coordinator(db)
    log_in(client, db, alex, NOW)
    stop_the_clock_at(NOW)
    return alex


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_only_the_coordinator_sees_and_changes_settings(client, db_with_sample_week, method):
    db = db_with_sample_week
    assert client.request(method, "/api/settings", json=as_sent()).status_code == 401
    log_in(client, db, make_staff(db, "Sam"), NOW)
    stop_the_clock_at(NOW)

    answer = client.request(method, "/api/settings", json=as_sent())

    assert answer.status_code == 403
    assert answer.json() == {"detail": "Only a coordinator can do this."}


def test_the_page_gets_every_setting_and_the_days_already_made(client, db_with_sample_week, alex_logged_in):
    make_pickup_day(db_with_sample_week, MONDAY)

    page = client.get("/api/settings").json()

    assert page["settings"] == as_sent()
    assert page["days_made"] == ["2026-11-09"]
    assert page["days_ahead"] == 7
    assert (page["changed_at"], page["changed_by"]) == (None, None)


def test_saving_from_the_page(client, db_with_sample_week, alex_logged_in):
    make_pickup_day(db_with_sample_week, MONDAY)  # booking opens at 5 pm, after NOW

    answer = client.put("/api/settings", json=as_sent(slot_capacity="2", booking_closes_time="11:30"))

    assert answer.status_code == 200
    page = answer.json()
    assert (page["settings"]["slot_capacity"], page["settings"]["booking_closes_time"]) == (2, "11:30")
    assert page["changed_by"] == "Alex"
    assert page["changed_at"] == "2026-11-08T16:00:00-03:30"
    assert page["capacity_changed_on"] == ["2026-11-09"]


def test_each_box_gets_its_own_message(client, db_with_sample_week, alex_logged_in):
    answer = client.put(
        "/api/settings",
        json=as_sent(slot_minutes="ten", pickup_gap_days=0, no_show_time="6 pm", substitute_limit=True),
    )

    assert answer.status_code == 422
    messages = {tuple(error["loc"][1:]): error["msg"] for error in answer.json()["detail"]}
    assert messages == {
        ("slot_minutes",): "Enter a whole number from 5 to 120.",
        ("pickup_gap_days",): "Enter a whole number from 1 to 365.",
        ("no_show_time",): "Enter a time, like 3:30 PM.",
        ("substitute_limit",): "Enter a whole number from 0 to 20.",
    }


def test_settings_that_dont_fit_get_a_sentence(client, db_with_sample_week, alex_logged_in):
    answer = client.put("/api/settings", json=as_sent(pickup_hours=[]))

    assert answer.status_code == 400
    assert answer.json() == {
        "detail": "Choose at least one pickup day of the week. To stop for a while, close the days instead."
    }
    assert len(db_with_sample_week.scalars(select(PickupHours)).all()) == 2
    assert db_with_sample_week.scalar(select(PickupDay)) is None
