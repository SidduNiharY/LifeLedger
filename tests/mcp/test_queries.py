from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.bills.schemas import BillStatus
from app.ledger.categories import Category
from app.ledger.schemas import Direction, TxnStatus
from app.mcp.queries import (
    spend_query,
    subscriptions_query,
    transactions_query,
    upcoming_bills_query,
)
from app.mcp.role import readonly_role_statements
from tests.factories import add_bill, add_txn, seed_november

TODAY = date(2026, 11, 6)


async def test_spend_query(session):
    await seed_november(session)
    assert await spend_query(session, None, None, TODAY) == {
        "month": "2026-11",
        "total": "3200.50",
        "income": "50000.00",
        "by_category": {"Food": "1650.00", "Bills": "1250.50", "Uncategorised": "300.00"},
    }
    assert await spend_query(session, "2026-11", "Food", TODAY) == {
        "month": "2026-11",
        "category": "Food",
        "total": "1650.00",
    }


async def test_transactions_query_rows(session):
    ids = await seed_november(session)
    [row] = await transactions_query(session, "2026-11", "Bills", 50, TODAY)
    assert row == {
        "id": ids["bills"],
        "date": "2026-11-04",
        "direction": "debit",
        "amount": "1250.50",
        "counterparty": "BESCOM",
        "category": "Bills",
    }


@pytest.mark.parametrize(
    "call,message",
    [
        (lambda s: spend_query(s, "2026-13", None, TODAY), "month must look like 2026-11"),
        (lambda s: spend_query(s, None, "Pizza", TODAY), "unknown category 'Pizza'"),
        (
            lambda s: transactions_query(s, None, None, 500, TODAY),
            "limit must be between 1 and 200",
        ),
        (lambda s: upcoming_bills_query(s, 0, TODAY), "days must be between 1 and 366"),
    ],
)
async def test_query_validation(session, call, message):
    with pytest.raises(ValueError, match=message):
        await call(session)


async def test_upcoming_bills_query(session):
    b1 = await add_bill(
        session,
        name="Internet",
        amount_due=Decimal("999.00"),
        due_on=TODAY + timedelta(days=5),
        status=BillStatus.OPEN,
    )
    b2 = await add_bill(
        session,
        name="Rent",
        amount_due=Decimal("25000.00"),
        due_on=TODAY - timedelta(days=2),
        status=BillStatus.OPEN,
    )
    await add_bill(
        session,
        name="Paid Electric",
        amount_due=Decimal("1200.00"),
        due_on=TODAY + timedelta(days=3),
        status=BillStatus.PAID,
    )

    rows = await upcoming_bills_query(session, days=30, today=TODAY)
    assert len(rows) == 2
    # Sorted by due_on asc
    assert rows[0] == {
        "id": b2.id,
        "name": "Rent",
        "amount_due": "25000.00",
        "due_on": (TODAY - timedelta(days=2)).isoformat(),
        "status": "open",
        "overdue": True,
    }
    assert rows[1] == {
        "id": b1.id,
        "name": "Internet",
        "amount_due": "999.00",
        "due_on": (TODAY + timedelta(days=5)).isoformat(),
        "status": "open",
        "overdue": False,
    }


async def test_subscriptions_query(session):
    for i in range(3):
        await add_txn(
            session,
            direction=Direction.DEBIT,
            amount=Decimal("649.00"),
            occurred_on=TODAY - timedelta(days=30 * (3 - i)),
            counterparty="Netflix India",
            merchant_key="NETFLIX",
            status=TxnStatus.CATEGORISED,
            category=Category.SUBSCRIPTIONS,
        )

    subs = await subscriptions_query(session, today=TODAY)
    assert len(subs) == 1
    assert subs[0]["merchant_key"] == "NETFLIX"
    assert subs[0]["amount"] == "649.00"
    assert subs[0]["count"] == 3


async def test_readonly_role_cannot_write(session):
    for stmt in readonly_role_statements():
        await session.execute(text(stmt))
    await session.execute(text("SET ROLE lifeledger_ro"))
    await session.execute(text("SELECT count(*) FROM transactions"))
    with pytest.raises(DBAPIError, match="permission denied"):
        await session.execute(
            text("INSERT INTO merchant_rules (merchant_key, category) VALUES ('X', 'Food')")
        )
