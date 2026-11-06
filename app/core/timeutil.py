"""Time helpers. Timestamps are UTC; dates shown to the user use a local zone (Asia/Kolkata)."""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo


def local_date(dt: datetime, tz: str) -> date:
    """The calendar date of an aware datetime in the given zone.

    Raises ValueError for a naive datetime and ZoneInfoNotFoundError for an unknown zone.
    """
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("local_date needs an aware datetime")
    return dt.astimezone(ZoneInfo(tz)).date()


def local_time_on(d: date, hour: int, tz: str) -> datetime:
    """The instant of `hour`:00 on date `d` in `tz`, as an aware UTC datetime.

    Raises ValueError if hour is outside 0-23 and ZoneInfoNotFoundError for an unknown zone.
    """
    return datetime.combine(d, time(hour), tzinfo=ZoneInfo(tz)).astimezone(UTC)


def format_day(d: date) -> str:
    """'Fri 20 Nov' (no zero padding, independent of platform strftime flags)."""
    return f"{d:%a} {d.day} {d:%b}"
