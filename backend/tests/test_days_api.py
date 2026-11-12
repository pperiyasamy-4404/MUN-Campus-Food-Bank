"""The coordinator's pickup days page, used the way the page uses it (S7, S9).

The rules are tested in test_day_changes.py. These check the answers the page
gets, that only the coordinator can change days, and what students then see.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import Category, Item, PickupDay, Slot, Variety
from app.services import booking as booking_rules
from app.services.booking import Choice
from app.services.pickup_days import make_pickup_day
from tests.helpers import MONDAY, THURSDAY, add, coordinator, log_in, make_staff, make_student, stop_the_clock_at

OPEN = datetime(2026, 11, 8, 21, 0, tzinfo=UTC)  # Sunday 5:30 pm
SUNDAY_4PM = datetime(2026, 11, 8, 19, 30, tzinfo=UTC)


@pytest.fixture
def week(client, db_with_sample_week):
    """Monday and Thursday are made. Ana has booked Monday. Alex, the coordinator, is logged in."""
    db = db_with_sample_week
    monday = make_pickup_day(db, MONDAY)
    make_pickup_day(db, THURSDAY)
    pantry = add(db, Category(name="Pantry"))
    oats = add(db, Variety(item_id=add(db, Item(name="Oats", category_id=pantry.id)).id, name="Quick oats", stock=5))
    ana = make_student(db)
    first = db.scalars(select(Slot).where(Slot.pickup_day_id == monday.id).order_by(Slot.starts_at)).first()
    booking_rules.hold_slot(db, ana, first.id, OPEN)
    booking_rules.book(db, ana, [Choice(oats.id)], [], OPEN)
    log_in(client, db, coordinator(db), OPEN)
    stop_the_clock_at(OPEN)
    return {"monday": monday, "ana": ana, "oats": oats}


@pytest.mark.parametrize(
    "method, address",
    [
        ("GET", "/api/coordinator/days"),
        ("POST", "/api/coordinator/days/2026-11-09/close"),
        ("POST", "/api/coordinator/days/close-range"),
        ("POST", "/api/coordinator/days/2026-11-09/reopen"),
        ("PUT", "/api/coordinator/days/2026-11-09/booking-times"),
        ("GET", "/api/totals"),
    ],
)
def test_only_the_coordinator_changes_days_and_sees_totals(client, db_with_sample_week, method, address):
    db = db_with_sample_week
    assert client.request(method, address, json={}).status_code == 401
    log_in(client, db, make_staff(db, "Sam"), OPEN)
    stop_the_clock_at(OPEN)

    answer = client.request(method, address, json={})

    assert answer.status_code == 403


def test_the_page_lists_the_days_with_their_bookings(client, week):
    page = client.get("/api/coordinator/days").json()

    assert page["pickup_weekdays"] == [1, 4]
    assert page["close_until"] == "2027-11-08"
    monday, thursday = page["days"]
    assert monday == {
        "pickup_date": "2026-11-09",
        "booking_opens_at": "2026-11-08T17:00:00-03:30",
        "booking_closes_at": "2026-11-09T12:00:00-03:30",
        "pickup_starts_at": "2026-11-09T15:30:00-03:30",
        "pickup_ends_at": "2026-11-09T17:30:00-03:30",
        "no_show_at": "2026-11-09T18:00:00-03:30",
        "booking_status": "open",
        "closed_reason": None,
        "booked": 1,
        "packed": 0,
        "why_not_close": None,
        "why_not_reopen": None,
        "why_not_move": None,
    }
    assert (thursday["pickup_date"], thursday["booked"]) == ("2026-11-12", 0)


def test_closing_a_day_from_the_page(client, week):
    answer = client.post("/api/coordinator/days/2026-11-09/close", json={"reason": "Snow storm"})

    assert answer.status_code == 200
    closed = answer.json()
    assert (closed["cancelled"], closed["were_packed"]) == (1, 0)
    assert closed["day"]["closed_reason"] == "Snow storm"
    assert closed["day"]["booking_status"] == "day_closed"
    assert closed["day"]["why_not_reopen"] == (
        "Closing Monday, November 9 cancelled 1 booking, so it stays closed: those students couldn't book it again."
    )
    assert week["oats"].stock == 5

    again = client.post("/api/coordinator/days/2026-11-09/close", json={"reason": "Snow storm"})
    assert again.status_code == 409
    assert again.json() == {"detail": "Monday, November 9 is closed already."}


def test_students_see_the_day_is_closed_and_why(client, db_with_sample_week, week):
    client.post("/api/coordinator/days/2026-11-09/close", json={"reason": "Snow storm"})
    log_in(client, db_with_sample_week, week["ana"], OPEN)

    mine = client.get("/api/my-booking").json()
    days = client.get("/api/pickup-days").json()

    assert mine["booking"] is None
    assert mine["closed_day"] == {"pickup_date": "2026-11-09", "reason": "Snow storm"}
    assert (days[0]["booking_status"], days[0]["closed_reason"]) == ("day_closed", "Snow storm")


def test_the_closed_day_message_goes_once_the_day_is_over(client, db_with_sample_week, week):
    client.post("/api/coordinator/days/2026-11-09/close", json={"reason": "Snow storm"})
    log_in(client, db_with_sample_week, week["ana"], OPEN)
    stop_the_clock_at(datetime(2026, 11, 9, 21, 30, tzinfo=UTC))  # Monday 6 pm

    assert client.get("/api/my-booking").json()["closed_day"] is None


def test_closing_a_date_further_ahead_from_the_page(client, db_with_sample_week, week):
    answer = client.post("/api/coordinator/days/2026-12-21/close", json={"reason": "Christmas break"})

    assert answer.status_code == 200
    assert answer.json()["day"]["closed_reason"] == "Christmas break"
    listed = [day["pickup_date"] for day in client.get("/api/coordinator/days").json()["days"]]
    assert listed == ["2026-11-09", "2026-11-12", "2026-12-21"]


def test_opening_a_day_again_from_the_page(client, db_with_sample_week, week):
    client.post("/api/coordinator/days/2026-11-12/close", json={"reason": "Wrong day"})

    answer = client.post("/api/coordinator/days/2026-11-12/reopen")

    assert answer.status_code == 200
    assert (answer.json()["closed_reason"], answer.json()["booking_status"]) == (None, "not_open_yet")


def test_a_missing_reason_gets_a_sentence(client, week):
    answer = client.post("/api/coordinator/days/2026-11-12/close", json={"reason": "  "})

    assert answer.status_code == 400
    assert answer.json() == {"detail": "Say why it's closed. Students see the reason."}


def test_booking_times_from_the_page_are_st_johns_time(client, db_with_sample_week, week):
    """The page's date-and-time boxes send no time zone: "2026-11-11T19:00" is 7 pm in St. John's."""
    answer = client.put(
        "/api/coordinator/days/2026-11-12/booking-times",
        json={"opens_at": "2026-11-11T19:00", "closes_at": "2026-11-12T11:00"},
    )

    assert answer.status_code == 200
    assert answer.json()["booking_opens_at"] == "2026-11-11T19:00:00-03:30"
    assert answer.json()["booking_closes_at"] == "2026-11-12T11:00:00-03:30"
    thursday = db_with_sample_week.scalar(select(PickupDay).where(PickupDay.pickup_date == THURSDAY))
    assert thursday.booking_opens_at == datetime(2026, 11, 11, 22, 30, tzinfo=UTC)


def test_moving_times_once_booking_is_over_is_refused(client, db_with_sample_week, week):
    monday_1230 = datetime(2026, 11, 9, 16, 0, tzinfo=UTC)
    log_in(client, db_with_sample_week, coordinator(db_with_sample_week, "Alex again"), monday_1230)
    stop_the_clock_at(monday_1230)

    answer = client.put(
        "/api/coordinator/days/2026-11-09/booking-times",
        json={"opens_at": "2026-11-08T17:00", "closes_at": "2026-11-09T13:00"},
    )

    assert answer.status_code == 400
    assert answer.json() == {"detail": "Booking for Monday, November 9 is over, and packing has started."}


# ---------- closing several days (decided 12 Nov) ----------


def test_closing_a_break_closes_made_and_later_days_and_skips_closed_ones(client, week, db_with_sample_week):
    """Monday 9 is booked, Thursday 12 is closed already, Monday 16 to Monday 23 aren't made yet."""
    client.post("/api/coordinator/days/2026-11-12/close", json={"reason": "Staff training"})

    answer = client.post(
        "/api/coordinator/days/close-range",
        json={"first": "2026-11-09", "last": "2026-11-23", "reason": "  Fall break,  back on 26 November "},
    )

    assert answer.status_code == 200
    assert answer.json() == {
        "closed": ["2026-11-09", "2026-11-16", "2026-11-19", "2026-11-23"],
        "cancelled": 1,
        "were_packed": 0,
        "skipped": ["Thursday, November 12 is closed already."],
    }
    days = {day.pickup_date.isoformat(): day.closed_reason for day in db_with_sample_week.scalars(select(PickupDay))}
    assert days == {
        "2026-11-09": "Fall break, back on 26 November",
        "2026-11-12": "Staff training",
        "2026-11-16": "Fall break, back on 26 November",
        "2026-11-19": "Fall break, back on 26 November",
        "2026-11-23": "Fall break, back on 26 November",
    }
    assert week["oats"].stock == 5


@pytest.mark.parametrize(
    "body, message",
    [
        ({"first": "2026-11-16", "last": "2026-11-09", "reason": "Break"}, "The last date is before the first date."),
        ({"first": "2026-11-17", "last": "2026-11-18", "reason": "Break"}, "There are no pickup days from Tuesday, November 17 to Wednesday, November 18."),
        ({"first": "2026-11-16", "last": "2028-01-01", "reason": "Break"}, "Dates can be closed up to a year ahead."),
        ({"first": "2026-11-16", "last": "2026-11-19", "reason": "   "}, "Say why it's closed. Students see the reason."),
    ],
)
def test_closing_several_days_needs_sensible_dates_and_a_reason(client, week, db_with_sample_week, body, message):
    answer = client.post("/api/coordinator/days/close-range", json=body)

    assert answer.status_code == 400
    assert answer.json() == {"detail": message}
    assert db_with_sample_week.scalar(select(PickupDay).where(PickupDay.closed_reason.is_not(None))) is None
