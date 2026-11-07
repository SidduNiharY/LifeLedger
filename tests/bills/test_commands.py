from datetime import date
from decimal import Decimal

import pytest

from app.bills.commands import ADDBILL_USAGE, ADDRENEWAL_USAGE, parse_addbill, parse_addrenewal
from app.bills.schemas import BillKind, Recurrence


def test_parse_addbill():
    d = parse_addbill(["Rent", "15000", "2026-12-05", "monthly"])
    assert (d.name, d.amount_due, d.due_on, d.recurrence, d.kind) == (
        "Rent",
        Decimal("15000.00"),
        date(2026, 12, 5),
        Recurrence.MONTHLY,
        BillKind.BILL,
    )
    assert (
        parse_addbill(["Electricity", "BESCOM", "1,250.50", "2026-11-20"]).name
        == "Electricity BESCOM"
    )


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["Rent"],
        ["Rent", "abc", "2026-12-05"],
        ["Rent", "15000", "05-12-2026"],
        ["15000", "2026-12-05"],
    ],
)
def test_parse_addbill_errors(args):
    assert parse_addbill(args) == ADDBILL_USAGE


def test_parse_addrenewal():
    d = parse_addrenewal(["Car", "insurance", "2027-01-10", "yearly"])
    assert (d.kind, d.name, d.amount_due, d.recurrence) == (
        BillKind.RENEWAL,
        "Car insurance",
        None,
        Recurrence.YEARLY,
    )
    assert parse_addrenewal(["Passport"]) == ADDRENEWAL_USAGE
    assert parse_addrenewal([]) == ADDRENEWAL_USAGE
    assert parse_addrenewal(["2027-01-10"]) == ADDRENEWAL_USAGE
    assert parse_addrenewal(["Car", "insurance", "10-01-2027"]) == ADDRENEWAL_USAGE
