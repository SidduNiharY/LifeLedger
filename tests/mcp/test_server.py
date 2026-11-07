from datetime import date
from decimal import Decimal

from app.ledger.categories import Category
from app.ledger.schemas import Direction, TxnStatus
from app.mcp.server import mcp, set_sessionmaker
from tests.factories import add_txn, seed_november

TODAY = date(2026, 11, 6)


async def test_exactly_four_tools():
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert names == {
        "get_spend",
        "list_transactions",
        "list_upcoming_bills",
        "list_subscriptions",
    }


async def test_server_tools_execution(sessionmaker, monkeypatch):
    set_sessionmaker(sessionmaker)
    monkeypatch.setattr("app.mcp.server.get_today", lambda: TODAY)

    async with sessionmaker() as s:
        ids = await seed_november(s)
        await add_txn(
            s,
            direction=Direction.DEBIT,
            amount=Decimal("649.00"),
            occurred_on=date(2026, 8, 6),
            counterparty="Netflix India",
            merchant_key="NETFLIX",
            status=TxnStatus.CATEGORISED,
            category=Category.SUBSCRIPTIONS,
        )
        await add_txn(
            s,
            direction=Direction.DEBIT,
            amount=Decimal("649.00"),
            occurred_on=date(2026, 9, 6),
            counterparty="Netflix India",
            merchant_key="NETFLIX",
            status=TxnStatus.CATEGORISED,
            category=Category.SUBSCRIPTIONS,
        )
        await add_txn(
            s,
            direction=Direction.DEBIT,
            amount=Decimal("649.00"),
            occurred_on=date(2026, 10, 6),
            counterparty="Netflix India",
            merchant_key="NETFLIX",
            status=TxnStatus.CATEGORISED,
            category=Category.SUBSCRIPTIONS,
        )
        await s.commit()

    spend = await mcp.call_tool("get_spend", {"month": "2026-11"})
    assert spend.structured_content["month"] == "2026-11"
    assert spend.structured_content["total"] == "3200.50"

    spend_food = await mcp.call_tool("get_spend", {"month": "2026-11", "category": "Food"})
    assert spend_food.structured_content == {
        "month": "2026-11",
        "category": "Food",
        "total": "1650.00",
    }

    txns = await mcp.call_tool("list_transactions", {"month": "2026-11", "category": "Bills"})
    assert len(txns.structured_content["result"]) == 1
    assert txns.structured_content["result"][0]["id"] == ids["bills"]

    bills = await mcp.call_tool("list_upcoming_bills", {"days": 30})
    assert isinstance(bills.structured_content["result"], list)

    subs = await mcp.call_tool("list_subscriptions", {})
    assert len(subs.structured_content["result"]) == 1
    assert subs.structured_content["result"][0]["merchant_key"] == "NETFLIX"
