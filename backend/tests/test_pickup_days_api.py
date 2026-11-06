"""GET /api/pickup-days: the upcoming pickup days and their slots."""

from datetime import UTC, date, time

from sqlalchemy import select

from app.models import Slot
from app.services.pickup_days import make_pickup_day, newfoundland_moment
from tests.helpers import stop_the_clock_at


def at(on: date, clock: time):
    """A Newfoundland clock time, as the UTC moment the server's clock would give."""
    return newfoundland_moment(on, clock).astimezone(UTC)


def pickup_days(client):
    response = client.get("/api/pickup-days")
    assert response.status_code == 200
    return response.json()


def test_a_day_comes_with_its_slots_in_newfoundland_time(client, db_with_sample_week):
    """Winter time is UTC-3:30, so the times end in -03:30 (T1)."""
    make_pickup_day(db_with_sample_week, date(2026, 11, 9))
    stop_the_clock_at(at(date(2026, 11, 4), time(12, 0)))

    [day] = pickup_days(client)

    assert day["pickup_date"] == "2026-11-09"
    assert day["booking_opens_at"] == "2026-11-08T17:00:00-03:30"
    assert day["booking_closes_at"] == "2026-11-09T12:00:00-03:30"
    assert day["booking_status"] == "not_open_yet"
    assert day["closed_reason"] is None
    # 3:30 to 5:30 pm in 10-minute slots: 12 of them, the last at 5:20 (S1).
    assert len(day["slots"]) == 12
    first = day["slots"][0]
    assert (first["starts_at"], first["places_left"]) == ("2026-11-09T15:30:00-03:30", 1)
    assert isinstance(first["id"], int)
    assert day["slots"][-1]["starts_at"] == "2026-11-09T17:20:00-03:30"


def test_a_summer_day_is_shown_in_summer_time(client, db_with_sample_week):
    """Summer time is UTC-2:30. The clock time students see stays 3:30 pm."""
    make_pickup_day(db_with_sample_week, date(2026, 7, 13))
    stop_the_clock_at(at(date(2026, 7, 1), time(9, 0)))

    [day] = pickup_days(client)

    assert day["booking_opens_at"] == "2026-07-12T17:00:00-02:30"
    assert day["slots"][0]["starts_at"] == "2026-07-13T15:30:00-02:30"


def test_past_days_are_left_out_and_today_is_kept(client, db_with_sample_week):
    for pickup_date in [date(2026, 11, 2), date(2026, 11, 5), date(2026, 11, 9)]:
        make_pickup_day(db_with_sample_week, pickup_date)
    stop_the_clock_at(at(date(2026, 11, 5), time(16, 0)))

    assert [day["pickup_date"] for day in pickup_days(client)] == ["2026-11-05", "2026-11-09"]


def test_today_means_today_in_newfoundland(client, db_with_sample_week):
    """At 11 pm on Thursday in St. John's it is already Friday in UTC. Thursday still counts as today."""
    make_pickup_day(db_with_sample_week, date(2026, 11, 5))
    stop_the_clock_at(at(date(2026, 11, 5), time(23, 0)))

    assert [day["pickup_date"] for day in pickup_days(client)] == ["2026-11-05"]


def test_booking_status_is_worked_out_from_the_clock(client, db_with_sample_week):
    make_pickup_day(db_with_sample_week, date(2026, 11, 9))
    stop_the_clock_at(at(date(2026, 11, 8), time(17, 0)))

    [day] = pickup_days(client)

    assert day["booking_status"] == "open"


def test_a_booked_slot_has_fewer_places_left(client, db_with_sample_week):
    day = make_pickup_day(db_with_sample_week, date(2026, 11, 9))
    first_slot = db_with_sample_week.scalars(
        select(Slot).where(Slot.pickup_day_id == day.id).order_by(Slot.starts_at).limit(1)
    ).one()
    first_slot.booked_count = 1
    db_with_sample_week.flush()
    stop_the_clock_at(at(date(2026, 11, 4), time(12, 0)))

    [day_out] = pickup_days(client)

    assert [slot["places_left"] for slot in day_out["slots"][:2]] == [0, 1]


def test_a_closed_day_says_why(client, db_with_sample_week):
    day = make_pickup_day(db_with_sample_week, date(2026, 11, 9))
    day.closed_at = at(date(2026, 11, 7), time(10, 0))
    day.closed_reason = "Snow storm"
    db_with_sample_week.flush()
    stop_the_clock_at(at(date(2026, 11, 8), time(18, 0)))

    [day_out] = pickup_days(client)

    assert day_out["booking_status"] == "day_closed"
    assert day_out["closed_reason"] == "Snow storm"


def test_no_pickup_days_is_an_empty_list(client, db_with_sample_week):
    assert pickup_days(client) == []

