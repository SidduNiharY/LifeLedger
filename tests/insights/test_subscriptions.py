from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.insights.subscriptions import Subscription, detect_subscriptions, render_subscriptions
from app.ledger.categories import Category as C
from app.ledger.models import Transaction
from app.ledger.schemas import Direction

TODAY = date(2026, 11, 1)


def charges(key, *items, category=C.SUBSCRIPTIONS):
    return [
        Transaction(
            id=i,
            direction=Direction.DEBIT,
            merchant_key=key,
            amount=Decimal(a),
            occurred_on=d,
            category=category,
        )
        for i, (a, d) in enumerate(items)
    ]


NETFLIX = charges(
    "NETFLIX",
    ("649.00", date(2026, 8, 4)),
    ("649.00", date(2026, 9, 4)),
    ("649.00", date(2026, 10, 4)),
)


@pytest.mark.parametrize(
    "txns,keys",
    [
        (NETFLIX, ["NETFLIX"]),
        (
            charges(
                "NETFLIX",
                ("499.00", date(2026, 7, 4)),
                ("649.00", date(2026, 8, 4)),
                ("649.00", date(2026, 9, 4)),
                ("649.00", date(2026, 10, 4)),
            ),
            ["NETFLIX"],
        ),
        (
            charges(
                "NETFLIX",
                ("649.00", date(2026, 8, 4)),
                ("649.00", date(2026, 9, 4)),
                ("799.00", date(2026, 10, 4)),
            ),
            [],
        ),
        (
            charges(
                "SWIGGY",
                ("300", date(2026, 10, 1)),
                ("410", date(2026, 10, 3)),
                ("280", date(2026, 10, 20)),
                ("350", date(2026, 11, 1)),
                category=C.FOOD,
            ),
            [],
        ),
        (
            charges(
                "NETFLIX",
                ("649.00", date(2026, 5, 4)),
                ("649.00", date(2026, 6, 4)),
                ("649.00", date(2026, 7, 4)),
            ),
            [],
        ),
        (
            charges(
                "LANDLORD",
                ("15000", date(2026, 8, 5)),
                ("15000", date(2026, 9, 5)),
                ("15000", date(2026, 10, 5)),
                category=C.RENT,
            ),
            [],
        ),
    ],
)
def test_detect_subscriptions(txns, keys):
    assert [s.merchant_key for s in detect_subscriptions(txns, TODAY)] == keys


def test_subscription_fields():
    [s] = detect_subscriptions(NETFLIX, TODAY)
    assert s == Subscription(
        merchant_key="NETFLIX",
        amount=Decimal("649.00"),
        last_seen=date(2026, 10, 4),
        next_expected=date(2026, 11, 3),
        count=3,
    )


def test_render_subscriptions():
    subs = [
        Subscription(
            merchant_key="NETFLIX",
            amount=Decimal("649.00"),
            last_seen=date(2026, 10, 4),
            next_expected=date(2026, 11, 3),
            count=3,
        ),
        Subscription(
            merchant_key="SPOTIFY",
            amount=Decimal("199.00"),
            last_seen=date(2026, 10, 14),
            next_expected=date(2026, 11, 14),
            count=3,
        ),
    ]
    assert render_subscriptions(subs) == (
        "🔁 Subscriptions (2), about ₹848.00 a month:\n"
        "• NETFLIX ₹649.00, next around Tue 3 Nov\n• SPOTIFY ₹199.00, next around Sat 14 Nov"
    )
    assert (
        render_subscriptions([])
        == "No subscriptions found yet. I need 3 monthly charges from the same merchant."
    )


async def test_subs_reply():
    from app.bot.actions import subs_reply

    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.all.return_value = NETFLIX
    session.scalars.return_value = result_mock
    res = await subs_reply(session, TODAY)
    assert "NETFLIX" in res
    assert "₹649.00" in res
    assert "next around Tue 3 Nov" in res
