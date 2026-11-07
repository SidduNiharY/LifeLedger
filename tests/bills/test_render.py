from datetime import date
from decimal import Decimal

import pytest

from app.bills.models import Bill
from app.bills.render import render_bill_reminder, render_due_list, render_new_bill
from app.bills.schemas import BillKind

BILL = Bill(
    id=12,
    kind=BillKind.BILL,
    name="Electricity",
    amount_due=Decimal("1250.50"),
    due_on=date(2026, 11, 20),
)
RENEWAL = Bill(
    id=13, kind=BillKind.RENEWAL, name="Passport renewal", amount_due=None, due_on=date(2026, 11, 9)
)


@pytest.mark.parametrize(
    "kind,text",
    [
        ("due_in_7", "⏰ Electricity: ₹1,250.50 due in 7 days (Fri 20 Nov)."),
        ("due_in_1", "⏰ Electricity: ₹1,250.50 due tomorrow (Fri 20 Nov)."),
        ("due_today", "⏰ Electricity: ₹1,250.50 due today (Fri 20 Nov)."),
        (
            "overdue",
            "⚠️ Electricity: ₹1,250.50 was due on Fri 20 Nov. "
            "No payment matched yet. Send /paid 12 if you paid.",
        ),
    ],
)
def test_render_bill_reminder(kind, text):
    assert render_bill_reminder(BILL, kind) == text


def test_render_renewal_and_new_bill():
    assert (
        render_bill_reminder(RENEWAL, "due_in_7")
        == "⏰ Passport renewal due in 7 days (Mon 9 Nov)."
    )
    assert render_new_bill(BILL) == (
        "📄 Added bill #12 Electricity: ₹1,250.50, due Fri 20 Nov. "
        "Reminders: 7 days before, 1 day before and on the day."
    )
    assert render_new_bill(RENEWAL) == (
        "📄 Added renewal #13 Passport renewal, due Mon 9 Nov. "
        "Reminders: 7 days before, 1 day before and on the day."
    )


def test_render_due_list():
    water = Bill(
        id=14,
        kind=BillKind.BILL,
        name="Water",
        amount_due=Decimal("300.00"),
        due_on=date(2026, 11, 2),
    )
    assert render_due_list([BILL, RENEWAL, water], date(2026, 11, 6)) == (
        "Due in the next 30 days:\n• #14 Water: ₹300.00 — Mon 2 Nov (overdue)\n"
        "• #13 Passport renewal — Mon 9 Nov\n• #12 Electricity: ₹1,250.50 — Fri 20 Nov"
    )
    assert render_due_list([], date(2026, 11, 6)) == "Nothing due in the next 30 days."
