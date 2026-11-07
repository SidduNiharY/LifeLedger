from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bills.repo import bills_due_within
from app.insights.subscriptions import Subscription, detect_subscriptions
from app.ledger.categories import SPEND_EXCLUDED
from app.ledger.models import Transaction
from app.ledger.repo import count_pending, month_spend
from app.ledger.schemas import Direction


class BillLine(BaseModel):
    id: int
    name: str
    amount_due: Decimal | None
    due_on: date


class Briefing(BaseModel):
    today: date
    yesterday_total: Decimal
    yesterday_top: list[tuple[str, Decimal]]
    month_total: Decimal
    bills_due: list[BillLine]
    subscriptions_due: list[Subscription]
    pending_questions: int


async def build_briefing(session: AsyncSession, today: date) -> Briefing:
    yesterday = today - timedelta(days=1)
    stmt = select(Transaction).where(
        Transaction.occurred_on == yesterday,
        Transaction.direction == Direction.DEBIT,
    )
    yesterday_all = (await session.scalars(stmt)).all()
    yesterday_txns = [t for t in yesterday_all if t.category not in SPEND_EXCLUDED]
    yesterday_total = sum((t.amount for t in yesterday_txns), start=Decimal("0.00"))

    cat_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for t in yesterday_txns:
        label = t.category.value if t.category is not None else "Uncategorised"
        cat_totals[label] += t.amount
    yesterday_top = sorted(cat_totals.items(), key=lambda item: item[1], reverse=True)[:3]

    month_summary = await month_spend(session, today.year, today.month)
    month_total = month_summary.total

    bills = await bills_due_within(session, today=today, days=7)
    bills_due = [
        BillLine(id=b.id, name=b.name, amount_due=b.amount_due, due_on=b.due_on) for b in bills
    ]

    since = today - timedelta(days=120)
    sub_txns_stmt = (
        select(Transaction)
        .where(
            Transaction.direction == Direction.DEBIT,
            Transaction.occurred_on >= since,
        )
        .order_by(Transaction.occurred_on.asc())
    )
    sub_txns = (await session.scalars(sub_txns_stmt)).all()
    all_subs = detect_subscriptions(sub_txns, today)
    subscriptions_due = [
        s for s in all_subs if today <= s.next_expected <= today + timedelta(days=7)
    ]
    subscriptions_due.sort(key=lambda s: (s.next_expected, s.merchant_key))

    pending_questions = await count_pending(session)

    return Briefing(
        today=today,
        yesterday_total=yesterday_total,
        yesterday_top=yesterday_top,
        month_total=month_total,
        bills_due=bills_due,
        subscriptions_due=subscriptions_due,
        pending_questions=pending_questions,
    )
