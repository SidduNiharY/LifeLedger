from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from app.bot.actions import (
    answer_category,
    fix_message,
    owner_only,
    parse_category_callback,
    recent_reply,
    review_messages,
    spend_reply,
)
from app.bot.main import build_application
from app.core.config import Settings
from app.ledger.categories import Category as C
from app.ledger.repo import lookup_merchant_category
from app.ledger.schemas import TxnStatus
from tests.factories import add_txn, seed_november

TODAY = date(2026, 11, 6)
PENDING = "Waiting for your answer: 1 (send /review)"


async def test_spend_reply(session):
    await seed_november(session)
    assert await spend_reply(session, None, TODAY) == (
        "Spend in Nov 2026: ₹3,200.50\n• Food: ₹1,650.00\n"
        "• Bills: ₹1,250.50\n• Uncategorised: ₹300.00\n"
        f"Income: ₹50,000.00\n{PENDING}"
    )
    assert (
        await spend_reply(session, "2026-10", TODAY)
        == f"Spend in Oct 2026: ₹999.00\n• Food: ₹999.00\n{PENDING}"
    )
    assert (
        await spend_reply(session, "2026-13", TODAY)
        == "Use /spend or /spend YYYY-MM, e.g. /spend 2026-10"
    )
    assert (
        await spend_reply(session, "invalid", TODAY)
        == "Use /spend or /spend YYYY-MM, e.g. /spend 2026-10"
    )


async def test_recent_reply(session):
    assert await recent_reply(session) == "No transactions yet."
    t = await add_txn(session, counterparty="Uber", category=C.TRAVEL)
    reply = await recent_reply(session)
    assert f"#{t.id}" in reply
    assert "Uber" in reply
    assert "Travel" in reply


async def test_answer_category_applies_to_same_merchant(session):
    a = await add_txn(
        session,
        counterparty="swiggy@icici",
        merchant_key="SWIGGY",
        status=TxnStatus.NEEDS_REVIEW,
        category=None,
    )
    await add_txn(
        session,
        counterparty="SWIGGY*BLR",
        merchant_key="SWIGGY",
        status=TxnStatus.NEEDS_REVIEW,
        category=None,
    )
    assert (
        await answer_category(session, f"cat:{a.id}:Food")
        == "✅ swiggy@icici → Food (also applied to 1 more)"
    )
    assert await lookup_merchant_category(session, "SWIGGY") is C.FOOD


async def test_stale_or_bad_buttons(session):
    for data in ["cat:abc:Food", "cat:999:Food", "cat:1:Pizza"]:
        assert await answer_category(session, data) == "That button has expired."


async def test_review_and_fix(session):
    assert [o.text for o in await review_messages(session)] == ["Nothing to review 🎉"]
    t = await add_txn(
        session, status=TxnStatus.NEEDS_REVIEW, category=None, suggested_category=C.TRAVEL
    )
    [msg] = await review_messages(session)
    assert msg.keyboard[0][0] == ("Travel ✓", f"cat:{t.id}:Travel")
    assert (await fix_message(session, "x")).text == "Use /fix <transaction number>, e.g. /fix 7"
    assert (await fix_message(session, "999")).text == "Transaction #999 not found."

    valid_fix = await fix_message(session, str(t.id))
    assert valid_fix.keyboard[0][0] == ("Travel ✓", f"cat:{t.id}:Travel")


def test_parse_category_callback():
    txn_id, cat = parse_category_callback("cat:42:Food")
    assert txn_id == 42
    assert cat is C.FOOD

    for invalid in ["cat:abc:Food", "cat:12:InvalidCat", "dog:1:Food", "cat:1"]:
        with pytest.raises(ValueError):
            parse_category_callback(invalid)


async def test_owner_only_drops_strangers():
    calls = []

    async def handler(update, context):
        calls.append(update.effective_chat.id)

    wrapped = owner_only(111)(handler)
    await wrapped(SimpleNamespace(effective_chat=SimpleNamespace(id=222)), None)
    await wrapped(SimpleNamespace(effective_chat=SimpleNamespace(id=111)), None)
    assert calls == [111]


def test_build_application():
    settings = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost/db",
        telegram_bot_token=SecretStr("123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"),
        telegram_owner_chat_id=12345,
    )
    sessionmaker = MagicMock()
    app = build_application(settings, sessionmaker)
    assert app is not None
    assert len(app.handlers[0]) == 5
