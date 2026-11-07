import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.inbound.models import InboundMessage, InboundSource, InboundStatus
from app.ledger.categories import Category
from app.ledger.models import Transaction
from app.ledger.schemas import (
    AlertExtraction,
    CategoryGuess,
    Direction,
    ParseMethod,
    TxnStatus,
)
from app.llm.ladder import ModelLadder, Runner
from app.pipeline.process import PipelineDeps
from tests.fakes import FakeRunner

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


async def add_inbound(
    session: AsyncSession,
    *,
    text: str | None,
    source: InboundSource = InboundSource.SMS,
    received_at: datetime = T0,
    status: InboundStatus = InboundStatus.RECEIVED,
    external_id: str | None = None,
    created_at: datetime | None = None,
    sender_trusted: bool = True,
    sender: str = "TEST_SENDER",
    subject: str | None = None,
) -> InboundMessage:
    if external_id is None:
        external_id = f"ext-{uuid.uuid4().hex[:12]}"
    kwargs: dict[str, Any] = dict(
        source=source,
        external_id=external_id,
        sender=sender,
        subject=subject,
        received_at=received_at,
        status=status,
        sender_trusted=sender_trusted,
        text=text,
    )
    if created_at is not None:
        kwargs["created_at"] = created_at
    msg = InboundMessage(**kwargs)
    session.add(msg)
    await session.flush()
    return msg


def make_deps(
    extract_local: Runner[AlertExtraction] | None = None,
    categorise_local: Runner[CategoryGuess] | None = None,
    cloud: Runner[Any] | None = None,
    threshold: float = 0.8,
    tz: str = "Asia/Kolkata",
) -> PipelineDeps:
    return PipelineDeps(
        extract=ModelLadder(
            local=extract_local or FakeRunner(),
            cloud=cloud,
            owner_names=[],
        ),
        categorise=ModelLadder(
            local=categorise_local or FakeRunner(),
            cloud=cloud,
            owner_names=[],
        ),
        threshold=threshold,
        tz=tz,
    )
