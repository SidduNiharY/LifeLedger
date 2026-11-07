import calendar
from collections.abc import Sequence
from datetime import date, datetime, timedelta

from app.bills.schemas import Recurrence, ReminderTime
from app.core.timeutil import local_date, local_time_on


def reminder_kind(days_before: int) -> str:
    """Return 'due_today' for 0, else 'due_in_{days_before}'."""
    if days_before == 0:
        return "due_today"
    return f"due_in_{days_before}"


def compute_reminder_times(
    due_on: date,
    now: datetime,
    days_before: Sequence[int] = (7, 1, 0),
    hour_local: int = 9,
    tz: str = "Asia/Kolkata",
) -> list[ReminderTime]:
    """Compute candidate reminder times strictly later than `now`, in chronological order.

    If no candidates remain:
    - [ReminderTime(at=now, kind="due_today")] if local_date(now, tz) <= due_on
    - [ReminderTime(at=now, kind="overdue")] if now has passed due_on
    """
    candidates: list[ReminderTime] = []
    for d in days_before:
        remind_at = local_time_on(due_on - timedelta(days=d), hour_local, tz)
        if remind_at > now:
            candidates.append(ReminderTime(at=remind_at, kind=reminder_kind(d)))

    if candidates:
        candidates.sort(key=lambda r: r.at)
        return candidates

    if local_date(now, tz) <= due_on:
        return [ReminderTime(at=now, kind="due_today")]
    return [ReminderTime(at=now, kind="overdue")]


def next_due_date(
    due_on: date,
    recurrence: Recurrence,
    anchor_day: int | None = None,
) -> date | None:
    """Calculate the next due date given the recurrence rule and anchor day.

    - NONE -> None
    - MONTHLY -> next month, clamping to the month's last day
    - YEARLY -> same month next year, handling Feb 29 -> Feb 28 on non-leap years
    """
    if recurrence == Recurrence.NONE:
        return None

    target_day = anchor_day or due_on.day

    if recurrence == Recurrence.MONTHLY:
        year = due_on.year
        month = due_on.month + 1
        if month > 12:
            month = 1
            year += 1
        _, max_days = calendar.monthrange(year, month)
        return date(year, month, min(target_day, max_days))

    if recurrence == Recurrence.YEARLY:
        year = due_on.year + 1
        month = due_on.month
        _, max_days = calendar.monthrange(year, month)
        return date(year, month, min(target_day, max_days))

    return None
