from datetime import date
from decimal import Decimal

from app.ledger.categories import Category as C
from app.ledger.models import Transaction
from app.ledger.schemas import Direction, SpendSummary
from app.notify.render import (
    category_keyboard,
    render_category_question,
    render_recent,
    render_spend,
)


def t(**kw):
    base = dict(
        id=7,
        direction=Direction.DEBIT,
        amount=Decimal("450.00"),
        counterparty="swiggy@icici",
        account_last4="1234",
        occurred_on=date(2026, 11, 5),
        category=C.FOOD,
    )
    return Transaction(**(base | kw))


def test_category_question():
    assert (
        render_category_question(t())
        == "₹450.00 debit · swiggy@icici · Thu 5 Nov\nA/c XX1234 · Which category?"
    )
    assert (
        render_category_question(t(counterparty=None, account_last4=None))
        == "₹450.00 debit · unknown payee · Thu 5 Nov\nWhich category?"
    )


def test_category_keyboard():
    kb = category_keyboard(42, C.FOOD)
    assert kb[0] == [("Food ✓", "cat:42:Food")]
    assert [len(r) for r in kb[1:]] == [3, 3, 3]
    assert [label for row in kb[1:] for label, _ in row] == [c.value for c in C if c is not C.FOOD]


def test_render_spend():
    s = SpendSummary(
        year=2026,
        month=11,
        total=Decimal("3200.50"),
        income=Decimal("50000.00"),
        by_category=[
            (C.FOOD, Decimal("1650.00")),
            (C.BILLS, Decimal("1250.50")),
            (None, Decimal("300.00")),
        ],
    )
    assert render_spend(s, pending=1) == (
        "Spend in Nov 2026: ₹3,200.50\n"
        "• Food: ₹1,650.00\n"
        "• Bills: ₹1,250.50\n"
        "• Uncategorised: ₹300.00\n"
        "Income: ₹50,000.00\nWaiting for your answer: 1 (send /review)"
    )


def test_render_spend_empty():
    s = SpendSummary(year=2026, month=12, total=Decimal("0"), income=Decimal("0"), by_category=[])
    assert render_spend(s, pending=0) == "No transactions recorded in Dec 2026."


def test_render_recent():
    assert render_recent([t(), t(id=8, category=None)]) == (
        "#7 Thu 5 Nov · ₹450.00 debit · swiggy@icici · Food\n"
        "#8 Thu 5 Nov · ₹450.00 debit · swiggy@icici · ❓"
    )
    assert render_recent([]) == "No transactions yet."
