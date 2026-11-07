from collections import defaultdict
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal

from pydantic import BaseModel

from app.core.money import format_inr
from app.core.timeutil import format_day
from app.ledger.categories import Category
from app.ledger.models import Transaction
from app.ledger.schemas import Direction

SUBSCRIPTION_EXCLUDED = frozenset(
    {
        Category.RENT,
        Category.EMI,
        Category.TRANSFER,
        Category.INCOME,
    }
)


class Subscription(BaseModel):
    merchant_key: str
    amount: Decimal
    last_seen: date
    next_expected: date
    count: int


def detect_subscriptions(txns: Sequence[Transaction], today: date) -> list[Subscription]:
    merchant_txns: dict[str, list[Transaction]] = defaultdict(list)
    for t in txns:
        if t.direction != Direction.DEBIT:
            continue
        if not t.merchant_key or not t.merchant_key.strip():
            continue
        if t.category in SUBSCRIPTION_EXCLUDED:
            continue
        merchant_txns[t.merchant_key].append(t)

    subs: list[Subscription] = []
    min_last_seen = today - timedelta(days=40)

    for m_key, charges in merchant_txns.items():
        if len(charges) < 3:
            continue
        charges.sort(key=lambda x: (x.occurred_on, x.id or 0))
        last_3 = charges[-3:]
        t1, t2, t3 = last_3

        gap1 = (t2.occurred_on - t1.occurred_on).days
        gap2 = (t3.occurred_on - t2.occurred_on).days
        if not (26 <= gap1 <= 35 and 26 <= gap2 <= 35):
            continue

        amounts = [t1.amount, t2.amount, t3.amount]
        median = sorted(amounts)[1]
        tolerance = median * Decimal("0.05")
        if any(abs(a - median) > tolerance for a in amounts):
            continue

        last_seen = t3.occurred_on
        if last_seen < min_last_seen:
            continue

        last_gap = t3.occurred_on - t2.occurred_on
        next_expected = last_seen + last_gap

        subs.append(
            Subscription(
                merchant_key=m_key,
                amount=t3.amount,
                last_seen=last_seen,
                next_expected=next_expected,
                count=len(charges),
            )
        )

    subs.sort(key=lambda s: (s.next_expected, s.merchant_key))
    return subs


def render_subscriptions(subs: list[Subscription]) -> str:
    if not subs:
        return "No subscriptions found yet. I need 3 monthly charges from the same merchant."
    total = sum((s.amount for s in subs), Decimal("0"))
    lines = [
        f"🔁 Subscriptions ({len(subs)}), about {format_inr(total)} a month:",
        *(
            f"• {s.merchant_key} {format_inr(s.amount)}, next around {format_day(s.next_expected)}"
            for s in subs
        ),
    ]
    return "\n".join(lines)
