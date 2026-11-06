from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.inbound.models import InboundSource
from app.ledger.categories import Category
from app.ledger.models import Transaction
from app.ledger.schemas import Direction, ParseMethod, TxnStatus

T0 = datetime(2026, 11, 5, 8, 52, tzinfo=UTC)


async def add_txn(session: AsyncSession, **overrides: Any) -> Transaction:
    base = dict(
        source=InboundSource.SMS,
        direction=Direction.DEBIT,
        amount=Decimal("100.00"),
        occurred_on=date(2026, 11, 5),
        received_at=T0,
        status=TxnStatus.CATEGORISED,
        category=Category.OTHER,
        parse_method=ParseMethod.RULE,
    )
    t = Transaction(**(base | overrides))
    session.add(t)
    await session.flush()
    return t


async def seed_november(session: AsyncSession) -> dict[str, int]:
    rows = {
        "food1": await add_txn(
            session,
            direction=Direction.DEBIT,
            amount=Decimal("450.00"),
            occurred_on=date(2026, 11, 5),
            counterparty="swiggy@icici",
            merchant_key="SWIGGY",
            status=TxnStatus.CATEGORISED,
            category=Category.FOOD,
        ),
        "food2": await add_txn(
            session,
            direction=Direction.DEBIT,
            amount=Decimal("1200.00"),
            occurred_on=date(2026, 11, 3),
            counterparty="ZOMATO",
            merchant_key="ZOMATO",
            status=TxnStatus.CATEGORISED,
            category=Category.FOOD,
        ),
        "bills": await add_txn(
            session,
            direction=Direction.DEBIT,
            amount=Decimal("1250.50"),
            occurred_on=date(2026, 11, 4),
            counterparty="BESCOM",
            merchant_key="BESCOM",
            status=TxnStatus.CATEGORISED,
            category=Category.BILLS,
        ),
        "pending": await add_txn(
            session,
            direction=Direction.DEBIT,
            amount=Decimal("300.00"),
            occurred_on=date(2026, 11, 2),
            counterparty="cafe@okaxis",
            merchant_key="CAFE",
            status=TxnStatus.NEEDS_REVIEW,
            suggested_category=Category.FOOD,
            category=None,
        ),
        "transfer": await add_txn(
            session,
            direction=Direction.DEBIT,
            amount=Decimal("10000.00"),
            occurred_on=date(2026, 11, 1),
            counterparty="HDFC CARD",
            merchant_key="HDFC CARD",
            status=TxnStatus.CATEGORISED,
            category=Category.TRANSFER,
        ),
        "salary": await add_txn(
            session,
            direction=Direction.CREDIT,
            amount=Decimal("50000.00"),
            occurred_on=date(2026, 11, 1),
            counterparty="ACME CORP PVT LTD",
            merchant_key="ACME",
            status=TxnStatus.CATEGORISED,
            category=Category.INCOME,
        ),
        "october": await add_txn(
            session,
            direction=Direction.DEBIT,
            amount=Decimal("999.00"),
            occurred_on=date(2026, 10, 30),
            counterparty="SWIGGY*BLR",
            merchant_key="SWIGGY",
            status=TxnStatus.CATEGORISED,
            category=Category.FOOD,
        ),
    }
    return {k: t.id for k, t in rows.items()}
