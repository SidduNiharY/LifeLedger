from datetime import UTC, date, datetime
from zoneinfo import ZoneInfoNotFoundError

import pytest

from app.core.timeutil import format_day, local_date, local_time_on


def test_format_day():
    assert format_day(date(2026, 11, 20)) == "Fri 20 Nov"
    assert format_day(date(2026, 11, 6)) == "Fri 6 Nov"


def test_local_time_on_is_utc():
    assert local_time_on(date(2026, 11, 20), 9, "Asia/Kolkata") == datetime(
        2026, 11, 20, 3, 30, tzinfo=UTC
    )


def test_local_time_on_result_is_aware_utc():
    result = local_time_on(date(2026, 11, 20), 9, "Asia/Kolkata")
    assert result.utcoffset().total_seconds() == 0


def test_local_date_crosses_midnight():
    assert local_date(datetime(2026, 11, 5, 20, 0, tzinfo=UTC), "Asia/Kolkata") == date(2026, 11, 6)


def test_local_date_same_day():
    assert local_date(datetime(2026, 11, 5, 10, 0, tzinfo=UTC), "Asia/Kolkata") == date(2026, 11, 5)


def test_local_date_rejects_naive_datetime():
    with pytest.raises(ValueError, match="local_date needs an aware datetime"):
        local_date(datetime(2026, 11, 5, 20, 0), "Asia/Kolkata")


@pytest.mark.parametrize("hour", [24, -1])
def test_local_time_on_rejects_bad_hour(hour):
    with pytest.raises(ValueError):
        local_time_on(date(2026, 11, 20), hour, "Asia/Kolkata")


def test_unknown_zone_raises():
    with pytest.raises(ZoneInfoNotFoundError):
        local_time_on(date(2026, 11, 20), 9, "Mars/Olympus")
    with pytest.raises(ZoneInfoNotFoundError):
        local_date(datetime(2026, 11, 5, tzinfo=UTC), "Mars/Olympus")
