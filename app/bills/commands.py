import re
from datetime import date

from app.bills.schemas import BillDraft, BillKind, BillSource, Recurrence
from app.core.money import parse_inr_amount

ADDBILL_USAGE = (
    "Usage: /addbill <name> <amount> <YYYY-MM-DD> [monthly|yearly]\n"
    "Example: /addbill Rent 15000 2026-12-05 monthly"
)
ADDRENEWAL_USAGE = (
    "Usage: /addrenewal <name> <YYYY-MM-DD> [yearly]\n"
    "Example: /addrenewal Passport renewal 2027-03-15"
)

_RECURRENCE_LOOKUP = {r.value: r for r in Recurrence if r != Recurrence.NONE}
_DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_addbill(args: list[str]) -> BillDraft | str:
    tokens = list(args)
    if not tokens:
        return ADDBILL_USAGE

    recurrence = Recurrence.NONE
    if tokens and tokens[-1].lower() in _RECURRENCE_LOOKUP:
        recurrence = _RECURRENCE_LOOKUP[tokens.pop().lower()]

    if not tokens:
        return ADDBILL_USAGE

    date_str = tokens.pop()
    if not _DATE_REGEX.fullmatch(date_str):
        return ADDBILL_USAGE
    try:
        due_on = date.fromisoformat(date_str)
    except ValueError:
        return ADDBILL_USAGE

    if not tokens:
        return ADDBILL_USAGE

    amount_str = tokens.pop()
    try:
        amount = parse_inr_amount(amount_str)
    except ValueError:
        return ADDBILL_USAGE

    name = " ".join(tokens).strip()
    if not name:
        return ADDBILL_USAGE

    try:
        return BillDraft(
            kind=BillKind.BILL,
            name=name,
            amount_due=amount,
            due_on=due_on,
            recurrence=recurrence,
            source=BillSource.MANUAL,
        )
    except Exception:
        return ADDBILL_USAGE


def parse_addrenewal(args: list[str]) -> BillDraft | str:
    tokens = list(args)
    if not tokens:
        return ADDRENEWAL_USAGE

    recurrence = Recurrence.NONE
    if tokens and tokens[-1].lower() in _RECURRENCE_LOOKUP:
        recurrence = _RECURRENCE_LOOKUP[tokens.pop().lower()]

    if not tokens:
        return ADDRENEWAL_USAGE

    date_str = tokens.pop()
    if not _DATE_REGEX.fullmatch(date_str):
        return ADDRENEWAL_USAGE
    try:
        due_on = date.fromisoformat(date_str)
    except ValueError:
        return ADDRENEWAL_USAGE

    name = " ".join(tokens).strip()
    if not name:
        return ADDRENEWAL_USAGE

    try:
        return BillDraft(
            kind=BillKind.RENEWAL,
            name=name,
            amount_due=None,
            due_on=due_on,
            recurrence=recurrence,
            source=BillSource.MANUAL,
        )
    except Exception:
        return ADDRENEWAL_USAGE
