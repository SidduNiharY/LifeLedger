from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.bills.schemas import BillStatus
from app.inbound.models import InboundSource
from app.inbound.models import InboundStatus as St
from app.ledger.categories import Category as C
from app.ledger.models import Transaction
from app.ledger.repo import remember_merchant
from app.ledger.schemas import (
    AlertExtraction,
    CategoryGuess,
    CategorySource,
    Direction,
    ParsedAlert,
    ParseMethod,
    TxnStatus,
)
from app.pipeline.process import process_inbound
from tests.factories import T0, add_bill, add_inbound, make_deps
from tests.fakes import FakeRunner
from tests.parsing.fixtures import OTP, S1, S2, S6


async def test_known_merchant_saved_without_llm(session):
    await remember_merchant(session, "SWIGGY", C.FOOD)
    inbound = await add_inbound(session, text=S1)
    r = await process_inbound(session, inbound, make_deps())
    assert r.status is St.PROCESSED and inbound.transaction_id == r.transaction.id
    assert (r.transaction.category, r.transaction.category_source, r.transaction.parse_method) == (
        C.FOOD,
        CategorySource.MEMORY,
        ParseMethod.RULE,
    )


async def test_low_confidence_needs_review(session):
    r = await process_inbound(
        session,
        await add_inbound(session, text=S1),
        make_deps(categorise_local=FakeRunner(CategoryGuess(category=C.FOOD, confidence=0.5))),
    )
    assert (r.transaction.status, r.transaction.category, r.transaction.suggested_category) == (
        TxnStatus.NEEDS_REVIEW,
        None,
        C.FOOD,
    )


async def test_otp_sms_is_ignored_without_llm(session):
    inbound = await add_inbound(session, text=OTP)
    r = await process_inbound(session, inbound, make_deps())
    assert (r.status, inbound.error) == (St.IGNORED, "otp")
    assert await session.scalar(select(func.count()).select_from(Transaction)) == 0


async def test_rule_miss_uses_llm_extraction(session):
    alert = ParsedAlert(
        direction=Direction.DEBIT,
        amount=Decimal("799.00"),
        account_last4="9012",
        counterparty="SPOTIFY",
    )
    r = await process_inbound(
        session,
        await add_inbound(session, text=S6),
        make_deps(
            extract_local=FakeRunner(AlertExtraction(is_transaction=True, alert=alert)),
            categorise_local=FakeRunner(CategoryGuess(category=C.SUBSCRIPTIONS, confidence=0.95)),
        ),
    )
    assert (r.transaction.parse_method, r.transaction.amount) == (
        ParseMethod.LOCAL_LLM,
        Decimal("799.00"),
    )
    assert str(r.transaction.occurred_on) == "2026-11-05"


async def test_llm_says_not_a_transaction(session):
    inbound = await add_inbound(
        session, text="Your card XX9012 statement is ready. Total 4,500.00 payable."
    )
    r = await process_inbound(
        session, inbound, make_deps(extract_local=FakeRunner(AlertExtraction(is_transaction=False)))
    )
    assert (r.status, inbound.error) == (St.IGNORED, "not_a_transaction")


async def test_same_payment_by_email_links_to_first(session):
    await remember_merchant(session, "SWIGGY", C.FOOD)
    first = await process_inbound(session, await add_inbound(session, text=S1), make_deps())
    email = await add_inbound(
        session, text=S1, source=InboundSource.EMAIL, received_at=T0 + timedelta(minutes=2)
    )
    r = await process_inbound(session, email, make_deps())
    assert (r.status, email.transaction_id) == (St.DUPLICATE, first.transaction.id)
    assert await session.scalar(select(func.count()).select_from(Transaction)) == 1


async def test_process_inbound_requires_received_status(session):
    inbound = await add_inbound(session, text=S1, status=St.PROCESSED)
    with pytest.raises(ValueError, match="RECEIVED"):
        await process_inbound(session, inbound, make_deps())


async def test_process_inbound_requires_text(session):
    inbound = await add_inbound(session, text=None)
    with pytest.raises(ValueError, match="text"):
        await process_inbound(session, inbound, make_deps())


async def test_saved_debit_closes_matching_bill(session):
    bill = await add_bill(
        session,
        name="Electricity",
        amount_due=Decimal("1250.50"),
        payee_keywords=["BESCOM"],
    )
    await remember_merchant(session, "BESCOM", C.BILLS)
    inbound = await add_inbound(session, text=S2)
    result = await process_inbound(session, inbound, make_deps())
    assert result.paid_bill_ids == [bill.id]
    assert len(result.outgoing) == 1
    assert result.outgoing[0].text.startswith(
        f"✅ ₹1,250.50 to BESCOM on Wed 4 Nov matched Electricity (#{bill.id})"
    )
    assert bill.status is BillStatus.PAID
