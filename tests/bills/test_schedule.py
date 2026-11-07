from datetime import UTC, date, datetime

import pytest

from app.bills.schedule import compute_reminder_times, next_due_date, reminder_kind
from app.bills.schemas import Recurrence as R

DUE = date(2026, 11, 20)


def at(day: int, h: int = 3, m: int = 30) -> datetime:
    return datetime(2026, 11, day, h, m, tzinfo=UTC)


def test_reminder_kind():
    assert reminder_kind(0) == "due_today"
    assert reminder_kind(1) == "due_in_1"
    assert reminder_kind(7) == "due_in_7"
    assert reminder_kind(3) == "due_in_3"


@pytest.mark.parametrize(
    "now,expected",
    [
        (at(6, 4, 0), [(at(13), "due_in_7"), (at(19), "due_in_1"), (at(20), "due_today")]),
        (at(18, 4, 0), [(at(19), "due_in_1"), (at(20), "due_today")]),
        (at(19, 22, 0), [(at(20), "due_today")]),
        (at(20, 5, 0), [(at(20, 5, 0), "due_today")]),
        (at(21, 2, 0), [(at(21, 2, 0), "overdue")]),
    ],
)
def test_compute_reminder_times(now, expected):
    assert [(r.at, r.kind) for r in compute_reminder_times(DUE, now)] == expected


@pytest.mark.parametrize(
    "due,rec,anchor,expected",
    [
        (date(2026, 1, 31), R.MONTHLY, 31, date(2026, 2, 28)),
        (date(2026, 2, 28), R.MONTHLY, 31, date(2026, 3, 31)),
        (date(2026, 12, 15), R.MONTHLY, 15, date(2027, 1, 15)),
        (date(2028, 2, 29), R.YEARLY, 29, date(2029, 2, 28)),
        (date(2026, 11, 20), R.NONE, None, None),
    ],
)
def test_next_due_date(due, rec, anchor, expected):
    assert next_due_date(due, rec, anchor) == expected
