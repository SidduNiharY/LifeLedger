import re
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bills.repo import bills_due_within
from app.insights.subscriptions import detect_subscriptions
from app.ledger.categories import Category
from app.ledger.models import Transaction
from app.ledger.repo import month_spend
from app.ledger.schemas import Direction

_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


def parse_month(value: str | None, today: date) -> tuple[int, int]:
    if value is None or not value.strip():
        return today.year, today.month
    m = _MONTH_RE.match(value.strip())
    if not m:
        raise ValueError("month must look like 2026-11")
    year, month = int(m.group(1)), int(m.group(2))
    if not (1 <= month <= 12):
        raise ValueError("month must look like 2026-11")
    return year, month


def parse_category(value: str | None) -> Category | None:
    if value is None or not value.strip():
        return None
    val = value.strip().casefold()
    for cat in Category:
        if cat.value.casefold() == val or cat.name.casefold() == val:
            return cat
    allowed = ", ".join(c.value for c in Category)
    raise ValueError(f"unknown category '{value}'; use one of: {allowed}")


async def spend_query(
    session: AsyncSession,
    month: str | None,
    category: str | None,
    today: date,
) -> dict:
    year, month_num = parse_month(month, today)
    cat = parse_category(category)
    spend = await month_spend(session, year, month_num)

    if cat is not None:
        cat_amount = Decimal("0.00")
        for c, amt in spend.by_category:
            if c == cat:
                cat_amount = amt
                break
        return {
            "month": f"{year:04d}-{month_num:02d}",
            "category": cat.value,
            "total": f"{cat_amount:.2f}",
        }

    by_category: dict[str, str] = {}
    for c, amt in spend.by_category:
        key = "Uncategorised" if c is None else c.value
        by_category[key] = f"{amt:.2f}"

    return {
        "month": f"{year:04d}-{month_num:02d}",
        "total": f"{spend.total:.2f}",
        "income": f"{spend.income:.2f}",
        "by_category": by_category,
    }


async def transactions_query(
    session: AsyncSession,
    month: str | None,
    category: str | None,
    limit: int = 50,
    today: date | None = None,
) -> list[dict]:
    if limit < 1 or limit > 200:
        raise ValueError("limit must be between 1 and 200")
    if today is None:
        today = date.today()

    year, month_num = parse_month(month, today)
    cat = parse_category(category)

    start_date = date(year, month_num, 1)
    next_month_date = date(year + 1, 1, 1) if month_num == 12 else date(year, month_num + 1, 1)

    stmt = select(Transaction).where(
        Transaction.direction == Direction.DEBIT,
        Transaction.occurred_on >= start_date,
        Transaction.occurred_on < next_month_date,
    )
    if cat is not None:
        stmt = stmt.where(Transaction.category == cat)

    stmt = stmt.order_by(Transaction.occurred_on.desc(), Transaction.id.desc()).limit(limit)
    txns = (await session.scalars(stmt)).all()

    return [
        {
            "id": t.id,
            "date": t.occurred_on.isoformat(),
            "direction": t.direction.value,
            "amount": f"{t.amount:.2f}",
            "counterparty": t.counterparty,
            "category": t.category.value if t.category else None,
        }
        for t in txns
    ]


async def upcoming_bills_query(
    session: AsyncSession,
    days: int = 30,
    today: date | None = None,
) -> list[dict]:
    if days < 1 or days > 366:
        raise ValueError("days must be between 1 and 366")
    if today is None:
        today = date.today()

    bills = await bills_due_within(session, today=today, days=days)
    return [
        {
            "id": b.id,
            "name": b.name,
            "amount_due": f"{b.amount_due:.2f}" if b.amount_due is not None else None,
            "due_on": b.due_on.isoformat(),
            "status": b.status.value,
            "overdue": b.due_on < today,
        }
        for b in bills
    ]


async def subscriptions_query(
    session: AsyncSession,
    today: date | None = None,
) -> list[dict]:
    if today is None:
        today = date.today()

    since = today - timedelta(days=120)
    stmt = (
        select(Transaction)
        .where(
            Transaction.direction == Direction.DEBIT,
            Transaction.occurred_on >= since,
        )
        .order_by(Transaction.occurred_on.asc())
    )
    txns = (await session.scalars(stmt)).all()
    subs = detect_subscriptions(txns, today)

    return [
        {
            "merchant_key": s.merchant_key,
            "amount": f"{s.amount:.2f}",
            "last_seen": s.last_seen.isoformat(),
            "next_expected": s.next_expected.isoformat(),
            "count": s.count,
        }
        for s in subs
    ]
