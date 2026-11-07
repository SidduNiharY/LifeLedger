from datetime import timedelta
from decimal import Decimal

from app.inbound.models import InboundSource
from app.ledger import repo
from app.ledger.categories import Category
from app.ledger.merchants import merchant_key
from app.ledger.schemas import CategoryDecision, ParseMethod, TxnStatus
from app.parsing.rules import parse_alert_text
from tests.factories import T0, add_txn, seed_november
from tests.parsing.fixtures import S1, S4

DONE = CategoryDecision(
    status=TxnStatus.CATEGORISED,
    category=Category.FOOD,
    suggested=Category.FOOD,
    source=None,
    confidence=None,
)
TZ = "Asia/Kolkata"


async def save(session, text, source, at):
    alert = parse_alert_text(text)
    return await repo.save_transaction(
        session,
        alert=alert,
        source=source,
        received_at=at,
        merchant_key=merchant_key(alert.counterparty),
        decision=DONE,
        parse_method=ParseMethod.RULE,
        tz=TZ,
    )


async def test_same_upi_ref_is_duplicate_across_channels(session):
    first = await save(session, S1, InboundSource.SMS, T0)
    dup = await repo.find_duplicate(
        session, parse_alert_text(S1), InboundSource.EMAIL, T0 + timedelta(minutes=2), TZ
    )
    assert dup.id == first.id


async def test_ref_on_sms_but_not_email_is_still_duplicate(session):
    first = await save(session, S1, InboundSource.SMS, T0)
    no_ref = parse_alert_text(S1).model_copy(update={"upi_ref": None})
    assert (
        await repo.find_duplicate(
            session, no_ref, InboundSource.EMAIL, T0 + timedelta(minutes=3), TZ
        )
    ).id == first.id


async def test_card_spend_on_sms_and_email_within_30_min_is_duplicate(session):
    first = await save(session, S4, InboundSource.SMS, T0)
    assert (
        await repo.find_duplicate(
            session, parse_alert_text(S4), InboundSource.EMAIL, T0 + timedelta(minutes=3), TZ
        )
    ).id == first.id


async def test_two_identical_card_spends_on_same_channel_are_not_duplicates(session):
    await save(session, S4, InboundSource.SMS, T0)
    assert (
        await repo.find_duplicate(
            session, parse_alert_text(S4), InboundSource.SMS, T0 + timedelta(minutes=10), TZ
        )
        is None
    )


async def test_other_channel_after_45_minutes_is_not_duplicate(session):
    await save(session, S4, InboundSource.SMS, T0)
    assert (
        await repo.find_duplicate(
            session, parse_alert_text(S4), InboundSource.EMAIL, T0 + timedelta(minutes=45), TZ
        )
        is None
    )


async def test_month_spend(session):
    await seed_november(session)
    s = await repo.month_spend(session, 2026, 11)
    assert s.total == Decimal("3200.50")
    assert s.by_category == [
        (Category.FOOD, Decimal("1650.00")),
        (Category.BILLS, Decimal("1250.50")),
        (None, Decimal("300.00")),
    ]
    assert s.income == Decimal("50000.00")


async def test_apply_user_category_teaches_merchant(session):
    a = await add_txn(session, merchant_key="SWIGGY", status=TxnStatus.NEEDS_REVIEW, category=None)
    b = await add_txn(session, merchant_key="SWIGGY", status=TxnStatus.NEEDS_REVIEW, category=None)
    await add_txn(session, merchant_key="ZOMATO", status=TxnStatus.NEEDS_REVIEW, category=None)
    assert await repo.apply_user_category(session, a.id, Category.FOOD) == [a.id, b.id]
    assert await repo.lookup_merchant_category(session, "SWIGGY") is Category.FOOD
    assert await repo.count_pending(session) == 1


async def test_save_transaction_persists_trace_id(session):
    alert = parse_alert_text(S1)
    decision = DONE.model_copy(update={"trace_id": "0af7651916cd43dd8448eb211c80319c"})
    t = await repo.save_transaction(
        session,
        alert=alert,
        source=InboundSource.SMS,
        received_at=T0,
        merchant_key=merchant_key(alert.counterparty),
        decision=decision,
        parse_method=ParseMethod.RULE,
        tz=TZ,
    )
    assert t.trace_id == "0af7651916cd43dd8448eb211c80319c"
