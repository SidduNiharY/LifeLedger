from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select

from app.bills.schemas import BillStatus, Recurrence
from app.ledger.schemas import Direction
from app.matching.models import MatchProposal
from app.matching.score import MatchLevel as L
from app.matching.service import answer_match, match_new_bills, match_transaction
from tests.factories import add_bill, add_txn

NOW = datetime(2026, 11, 18, 6, 0, tzinfo=UTC)


def debit(session, **kw):
    base = dict(
        direction=Direction.DEBIT,
        amount=Decimal("1250.50"),
        merchant_key="BESCOM",
        counterparty="BESCOM",
        occurred_on=date(2026, 11, 18),
    )
    return add_txn(session, **(base | kw))


async def test_exact_debit_closes_bill(session):
    b, t = await add_bill(session), await debit(session)
    out = await match_transaction(session, t, NOW)
    assert (out.level, out.paid_bill_ids, b.status, b.paid_transaction_id) == (
        L.EXACT,
        [b.id],
        BillStatus.PAID,
        t.id,
    )
    assert (
        out.outgoing[0].text
        == f"✅ ₹1,250.50 to BESCOM on Wed 18 Nov matched Electricity (#{b.id}). "
        "Marked paid, reminders stopped."
    )


async def test_probable_debit_asks(session):
    b, t = await add_bill(session), await debit(session, merchant_key="PAYTM", counterparty="PAYTM")
    out = await match_transaction(session, t, NOW)
    p = (await session.scalars(select(MatchProposal))).one()
    assert (out.level, b.status, p.status.value) == (L.PROBABLE, BillStatus.OPEN, "pending")
    assert (
        out.outgoing[0].text
        == f"❓ Is ₹1,250.50 to PAYTM on Wed 18 Nov the payment for Electricity (#{b.id}, "
        "₹1,250.50 due Fri 20 Nov)?"
    )
    assert out.outgoing[0].keyboard == [[("Yes", f"match:{p.id}:y"), ("No", f"match:{p.id}:n")]]


async def test_credit_never_matches(session):
    await add_bill(session)
    assert (
        await match_transaction(session, await debit(session, direction=Direction.CREDIT), NOW)
    ).level is L.NONE


async def test_rejected_pair_not_asked_again(session):
    await add_bill(session)
    t = await debit(session, merchant_key="PAYTM", counterparty="PAYTM")
    p_out = await match_transaction(session, t, NOW)
    pid = (await session.scalars(select(MatchProposal))).one().id
    assert await answer_match(session, f"match:{pid}:n", NOW) == ("OK, not linked.", [])
    assert (await match_transaction(session, t, NOW)).level is L.NONE and p_out.level is L.PROBABLE


async def test_one_payment_closes_one_bill(session):
    nov = await add_bill(
        session,
        name="Rent",
        amount_due=Decimal("15000"),
        due_on=date(2026, 11, 5),
        payee_keywords=["LANDLORD"],
    )
    dec = await add_bill(
        session,
        name="Rent",
        amount_due=Decimal("15000"),
        due_on=date(2026, 12, 5),
        payee_keywords=["LANDLORD"],
    )
    t = await debit(
        session,
        amount=Decimal("15000"),
        merchant_key="LANDLORD",
        counterparty="landlord@okicici",
        occurred_on=date(2026, 11, 6),
    )
    await match_transaction(session, t, NOW)
    assert (nov.status, dec.status) == (BillStatus.PAID, BillStatus.OPEN)
    assert (await match_transaction(session, t, NOW)).level is L.NONE


async def test_late_payment_closes_expired_bill(session):
    b = await add_bill(session, status=BillStatus.EXPIRED)
    out = await match_transaction(
        session, await debit(session, occurred_on=date(2026, 11, 25)), NOW
    )
    assert (out.level, b.status) == (L.EXACT, BillStatus.PAID)


async def test_answer_twice_is_harmless(session):
    b = await add_bill(session, recurrence=Recurrence.MONTHLY, anchor_day=20)
    await match_transaction(
        session, await debit(session, merchant_key="PAYTM", counterparty="PAYTM"), NOW
    )
    pid = (await session.scalars(select(MatchProposal))).one().id
    assert await answer_match(session, f"match:{pid}:y", NOW) == (
        f"✅ Electricity (#{b.id}) marked paid. Next one: Sun 20 Dec.",
        [b.id],
    )
    assert await answer_match(session, f"match:{pid}:y", NOW) == (
        f"Electricity (#{b.id}) is already paid.",
        [],
    )
    assert await answer_match(session, "match:999:y", NOW) == ("That question has expired.", [])


async def test_new_bill_matches_earlier_payment(session):
    t = await debit(session, occurred_on=date(2026, 11, 3))
    b = await add_bill(session)
    out = await match_new_bills(session, NOW)
    assert (out.paid_bill_ids, b.paid_transaction_id) == ([b.id], t.id)
    assert await session.scalar(select(func.count()).select_from(MatchProposal)) == 0
