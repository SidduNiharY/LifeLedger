from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.state import get_state, set_state
from app.inbound.models import InboundMessage, InboundSource, InboundStatus
from app.ledger.categories import Category
from app.ledger.models import Transaction
from app.ledger.schemas import AlertExtraction, Direction, ParsedAlert, ParseMethod, TxnStatus

T0 = datetime(2026, 11, 4, 6, 0, tzinfo=UTC)


def txn(**kw):
    base = dict(
        source=InboundSource.SMS,
        direction=Direction.DEBIT,
        amount=Decimal("1250.50"),
        occurred_on=date(2026, 11, 4),
        received_at=T0,
        status=TxnStatus.CATEGORISED,
        category=Category.BILLS,
        parse_method=ParseMethod.RULE,
    )
    return Transaction(**(base | kw))


async def test_amount_round_trips_as_decimal(session):
    t = txn()
    session.add(t)
    await session.flush()
    txn_id = t.id
    session.expire_all()
    got = await session.get(Transaction, txn_id)
    assert got.amount == Decimal("1250.50") and isinstance(got.amount, Decimal)
    assert got.direction is Direction.DEBIT


async def test_dedupe_ref_unique(session):
    session.add_all([txn(dedupe_ref="upi:432112345678"), txn(dedupe_ref="upi:432112345678")])
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_inbound_external_id_unique_per_source(session):
    def msg(source):
        return InboundMessage(
            source=source,
            external_id="abc",
            sender="VM-HDFCBK",
            received_at=T0,
            status=InboundStatus.RECEIVED,
            sender_trusted=True,
        )

    session.add_all([msg(InboundSource.SMS), msg(InboundSource.EMAIL)])
    await session.flush()
    session.add(msg(InboundSource.SMS))
    with pytest.raises(IntegrityError):
        await session.flush()


def test_parsed_alert_validation():
    with pytest.raises(ValidationError):
        ParsedAlert(direction=Direction.DEBIT, amount=Decimal("0"))
    with pytest.raises(ValidationError):
        ParsedAlert(direction=Direction.DEBIT, amount=Decimal("1"), upi_ref="123")
    with pytest.raises(ValidationError):
        AlertExtraction(is_transaction=True, alert=None)


async def test_state_round_trip(session):
    assert await get_state(session, "gmail_last_success") is None
    await set_state(session, "gmail_last_success", "2026-11-06T00:00:00+00:00")
    await set_state(session, "gmail_last_success", "2026-11-07T00:00:00+00:00")
    assert await get_state(session, "gmail_last_success") == "2026-11-07T00:00:00+00:00"


# --- additional tests ---


async def test_enums_stored_as_values(session):
    t = txn(category_source=None)
    session.add(t)
    await session.flush()
    row = (
        await session.execute(
            text("select source, direction, status, category, parse_method from transactions")
        )
    ).one()
    assert tuple(row) == ("sms", "debit", "categorised", "Bills", "rule")


async def test_amount_must_be_positive(session):
    session.add(txn(amount=Decimal("0")))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_null_dedupe_refs_do_not_collide(session):
    session.add_all([txn(), txn()])
    await session.flush()


async def test_truncate_isolates_tests_a(session):
    session.add(txn())
    await session.commit()


async def test_truncate_isolates_tests_b(session):
    count = (await session.execute(text("select count(*) from transactions"))).scalar_one()
    assert count == 0


def test_alert_extraction_rejects_alert_when_not_transaction():
    alert = ParsedAlert(direction=Direction.CREDIT, amount=Decimal("10.00"))
    with pytest.raises(ValidationError):
        AlertExtraction(is_transaction=False, alert=alert)
    assert AlertExtraction(is_transaction=False).alert is None
