from datetime import date
from decimal import Decimal

from app.briefing.build import BillLine, Briefing
from app.briefing.render import render_briefing
from app.insights.subscriptions import Subscription

TODAY = date(2026, 11, 6)


def test_render_briefing_full():
    b = Briefing(
        today=TODAY,
        yesterday_total=Decimal("1900.00"),
        yesterday_top=[("Food", Decimal("1650.00")), ("Bills", Decimal("250.00"))],
        month_total=Decimal("3200.50"),
        bills_due=[
            BillLine(id=14, name="Water", amount_due=Decimal("300.00"), due_on=date(2026, 11, 2)),
            BillLine(id=13, name="Passport renewal", amount_due=None, due_on=date(2026, 11, 9)),
            BillLine(
                id=12, name="Electricity", amount_due=Decimal("1250.50"), due_on=date(2026, 11, 13)
            ),
        ],
        subscriptions_due=[
            Subscription(
                merchant_key="NETFLIX",
                amount=Decimal("649.00"),
                last_seen=date(2026, 10, 10),
                next_expected=date(2026, 11, 10),
                count=3,
            )
        ],
        pending_questions=2,
    )
    assert render_briefing(b) == (
        "☀️ Good morning! Fri 6 Nov\n"
        "Yesterday: ₹1,900.00 (Food ₹1,650.00, Bills ₹250.00)\n"
        "November so far: ₹3,200.50\n"
        "Due this week:\n"
        "• #14 Water: ₹300.00, Mon 2 Nov (overdue)\n"
        "• #13 Passport renewal, Mon 9 Nov\n"
        "• #12 Electricity: ₹1,250.50, Fri 13 Nov\n"
        "Subscriptions this week: NETFLIX ₹649.00 (around Tue 10 Nov)\n"
        "2 transactions need a category. Send /review"
    )


def test_render_briefing_quiet_day():
    b = Briefing(
        today=TODAY,
        yesterday_total=Decimal("0"),
        yesterday_top=[],
        month_total=Decimal("0"),
        bills_due=[],
        subscriptions_due=[],
        pending_questions=1,
    )
    assert render_briefing(b) == (
        "☀️ Good morning! Fri 6 Nov\nYesterday: no spending\nNovember so far: ₹0.00\n"
        "Nothing due this week.\n1 transaction needs a category. Send /review"
    )
