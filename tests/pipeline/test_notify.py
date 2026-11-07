from datetime import date
from decimal import Decimal

from app.ledger.categories import Category
from app.ledger.models import Transaction
from app.ledger.schemas import Direction
from app.pipeline.notify import review_notifications


def txns(n):
    return [
        Transaction(
            id=i,
            direction=Direction.DEBIT,
            amount=Decimal("10"),
            counterparty="cafe@okaxis",
            occurred_on=date(2026, 11, 5),
            suggested_category=Category.FOOD,
        )
        for i in range(n)
    ]


def test_few_reviews_are_individual_questions():
    out = review_notifications(txns(3))
    assert len(out) == 3 and out[0].keyboard[0][0][1] == "cat:0:Food"


def test_single_review_question():
    out = review_notifications(txns(1))
    assert len(out) == 1
    assert "Which category?" in out[0].text
    assert out[0].keyboard[0][0] == ("Food ✓", "cat:0:Food")


def test_empty_reviews_returns_empty():
    assert review_notifications([]) == []


def test_many_reviews_become_one_summary():
    assert [o.text for o in review_notifications(txns(5))] == [
        "📝 5 new transactions need a category. Send /review to answer them."
    ]
