from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import local_date
from app.inbound.models import InboundSource
from app.ledger.categories import SPEND_EXCLUDED, Category
from app.ledger.merchants import merchant_key as compute_merchant_key
from app.ledger.models import MerchantRule, Transaction
from app.ledger.schemas import (
    CategoryDecision,
    CategorySource,
    Direction,
    ParsedAlert,
    ParseMethod,
    SpendSummary,
    TxnStatus,
)


def dedupe_ref_for(alert: ParsedAlert) -> str | None:
    return f"upi:{alert.upi_ref}" if alert.upi_ref else None


async def find_duplicate(
    session: AsyncSession,
    alert: ParsedAlert,
    source: InboundSource,
    received_at: datetime,
    tz: str,
    window: timedelta = timedelta(minutes=30),
) -> Transaction | None:
    ref = dedupe_ref_for(alert)
    if ref:
        stmt = select(Transaction).where(Transaction.dedupe_ref == ref)
        match = await session.scalar(stmt)
        if match:
            return match

    occurred_on = alert.occurred_on or local_date(received_at, tz)
    m_key = compute_merchant_key(alert.counterparty)

    stmt = select(Transaction).where(
        Transaction.account_last4 == alert.account_last4,
        Transaction.direction == alert.direction,
        Transaction.amount == alert.amount,
        Transaction.occurred_on == occurred_on,
        Transaction.merchant_key.is_not_distinct_from(m_key),
        Transaction.source != source,
        Transaction.received_at >= received_at - window,
        Transaction.received_at <= received_at + window,
    )
    return await session.scalar(stmt)


async def save_transaction(
    session: AsyncSession,
    *,
    alert: ParsedAlert,
    source: InboundSource,
    received_at: datetime,
    merchant_key: str | None,
    decision: CategoryDecision,
    parse_method: ParseMethod,
    tz: str,
) -> Transaction:
    occurred_on = alert.occurred_on or local_date(received_at, tz)
    t = Transaction(
        source=source,
        dedupe_ref=dedupe_ref_for(alert),
        account_last4=alert.account_last4,
        direction=alert.direction,
        amount=alert.amount,
        counterparty=alert.counterparty,
        merchant_key=merchant_key,
        occurred_on=occurred_on,
        received_at=received_at,
        status=decision.status,
        category=decision.category,
        suggested_category=decision.suggested,
        category_source=decision.source,
        category_confidence=decision.confidence,
        parse_method=parse_method,
        trace_id=decision.trace_id,
    )
    session.add(t)
    await session.flush()
    return t


async def lookup_merchant_category(session: AsyncSession, merchant_key: str) -> Category | None:
    rule = await session.get(MerchantRule, merchant_key)
    return rule.category if rule else None


async def remember_merchant(session: AsyncSession, merchant_key: str, category: Category) -> None:
    stmt = (
        insert(MerchantRule)
        .values(merchant_key=merchant_key, category=category)
        .on_conflict_do_update(
            index_elements=[MerchantRule.merchant_key],
            set_=dict(category=category, updated_at=func.now()),
        )
    )
    await session.execute(stmt)
    await session.flush()


async def apply_user_category(session: AsyncSession, txn_id: int, category: Category) -> list[int]:
    t = await session.get(Transaction, txn_id)
    if not t:
        raise LookupError(f"Transaction #{txn_id} not found")

    t.category = category
    t.category_source = CategorySource.USER
    t.status = TxnStatus.CATEGORISED
    updated_ids = [t.id]

    if t.merchant_key:
        await remember_merchant(session, t.merchant_key, category)
        stmt = select(Transaction).where(
            Transaction.merchant_key == t.merchant_key,
            Transaction.status == TxnStatus.NEEDS_REVIEW,
            Transaction.id != t.id,
        )
        others = (await session.scalars(stmt)).all()
        for o in others:
            o.category = category
            o.category_source = CategorySource.USER
            o.status = TxnStatus.CATEGORISED
            updated_ids.append(o.id)

    await session.flush()
    return updated_ids


async def month_spend(session: AsyncSession, year: int, month: int) -> SpendSummary:
    start_date = date(year, month, 1)
    next_month_date = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    txns_stmt = select(Transaction).where(
        Transaction.occurred_on >= start_date,
        Transaction.occurred_on < next_month_date,
    )
    txns = (await session.scalars(txns_stmt)).all()

    income = Decimal("0.00")
    total = Decimal("0.00")
    cat_totals: dict[Category | None, Decimal] = defaultdict(lambda: Decimal("0.00"))

    for t in txns:
        if t.direction == Direction.CREDIT:
            income += t.amount
        elif t.direction == Direction.DEBIT:
            if t.category not in SPEND_EXCLUDED:
                total += t.amount
                cat_totals[t.category] += t.amount

    by_category = sorted(cat_totals.items(), key=lambda item: item[1], reverse=True)

    return SpendSummary(
        year=year,
        month=month,
        total=total,
        by_category=by_category,
        income=income,
    )


async def count_pending(session: AsyncSession) -> int:
    stmt = (
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.status == TxnStatus.NEEDS_REVIEW)
    )
    return await session.scalar(stmt) or 0


async def pending_review(session: AsyncSession, limit: int = 10) -> list[Transaction]:
    stmt = (
        select(Transaction)
        .where(Transaction.status == TxnStatus.NEEDS_REVIEW)
        .order_by(Transaction.occurred_on.asc(), Transaction.id.asc())
        .limit(limit)
    )
    return list((await session.scalars(stmt)).all())


async def recent_transactions(session: AsyncSession, limit: int = 10) -> list[Transaction]:
    stmt = (
        select(Transaction)
        .order_by(Transaction.occurred_on.desc(), Transaction.id.desc())
        .limit(limit)
    )
    return list((await session.scalars(stmt)).all())
