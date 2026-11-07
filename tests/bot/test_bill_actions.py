from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

from app.bot.actions import (
    addbill_reply,
    addrenewal_reply,
    cancelbill_reply,
    due_reply,
    paid_reply,
)

NOW = datetime(2026, 12, 1, 6, 0, tzinfo=UTC)
RENT = ["Rent", "15000", "2026-12-05", "monthly"]


async def test_addbill_and_duplicate(session):
    assert await addbill_reply(session, RENT) == (
        "📄 Added bill #1 Rent: ₹15,000.00, due Sat 5 Dec. "
        "Reminders: 7 days before, 1 day before and on the day."
    )
    assert await addbill_reply(session, RENT) == "That bill already exists as #1."


async def test_addrenewal_reply(session):
    reply = await addrenewal_reply(session, ["Passport", "renewal", "2027-03-15", "yearly"])
    assert "📄 Added renewal #1 Passport renewal, due Mon 15 Mar." in reply
    assert (
        await addrenewal_reply(session, ["Passport", "renewal", "2027-03-15"])
        == "That bill already exists as #1."
    )


async def test_due_reply(session):
    today = date(2026, 12, 1)
    assert await due_reply(session, today) == "Nothing due in the next 30 days."

    await addbill_reply(session, RENT)
    reply = await due_reply(session, today)
    assert "Due in the next 30 days:" in reply
    assert "• #1 Rent: ₹15,000.00 — Sat 5 Dec" in reply


async def test_paid_reply(session):
    await addbill_reply(session, RENT)
    assert await paid_reply(session, "1", NOW) == (
        "✅ Marked #1 Rent as paid. Next one: Tue 5 Jan.",
        1,
    )
    assert await paid_reply(session, "1", NOW) == ("#1 Rent is already paid.", None)
    assert await paid_reply(session, "99", NOW) == ("Bill #99 not found.", None)
    assert await paid_reply(session, "x", NOW) == ("Use /paid <bill number>, e.g. /paid 12", None)


async def test_cancelbill_reply(session):
    await addbill_reply(session, ["Gym", "1500", "2026-12-10"])
    assert await cancelbill_reply(session, "1") == ("🗑️ Cancelled #1 Gym. No more reminders.", 1)
    assert await cancelbill_reply(session, "1") == ("#1 Gym is already cancelled.", None)
    assert await cancelbill_reply(session, "99") == ("Bill #99 not found.", None)
    assert await cancelbill_reply(session, "bad") == (
        "Use /cancelbill <bill number>, e.g. /cancelbill 12",
        None,
    )


async def test_bot_paid_and_cancel_handlers_signal_workflows(session):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from pydantic import SecretStr

    from app.bot.main import build_application
    from app.core.config import Settings

    @asynccontextmanager
    async def mock_sessionmaker():
        yield session

    settings = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost/db",
        telegram_bot_token=SecretStr("123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"),
        telegram_owner_chat_id=12345,
    )

    workflows = MagicMock()
    workflows.mark_paid = AsyncMock()
    workflows.cancel = AsyncMock()

    app = build_application(settings, mock_sessionmaker, workflows=workflows)

    handlers_by_cmd = {
        list(h.commands)[0]: h.callback for h in app.handlers[0] if hasattr(h, "commands")
    }

    # Add a bill first via addbill handler
    msg_add = SimpleNamespace(reply_text=AsyncMock())
    update_add = SimpleNamespace(
        effective_chat=SimpleNamespace(id=12345),
        effective_message=msg_add,
    )
    ctx_add = SimpleNamespace(args=["Rent", "15000", "2026-12-05", "monthly"])
    await handlers_by_cmd["addbill"](update_add, ctx_add)
    assert "Added bill #1" in msg_add.reply_text.call_args[0][0]

    # Test paid handler
    msg_paid = SimpleNamespace(reply_text=AsyncMock())
    update_paid = SimpleNamespace(
        effective_chat=SimpleNamespace(id=12345),
        effective_message=msg_paid,
    )
    ctx_paid = SimpleNamespace(args=["1"])
    await handlers_by_cmd["paid"](update_paid, ctx_paid)

    workflows.mark_paid.assert_awaited_once_with(1)
    assert "Marked #1 Rent as paid" in msg_paid.reply_text.call_args[0][0]

    # Add another bill to test cancelbill handler
    msg_add2 = SimpleNamespace(reply_text=AsyncMock())
    update_add2 = SimpleNamespace(
        effective_chat=SimpleNamespace(id=12345),
        effective_message=msg_add2,
    )
    ctx_add2 = SimpleNamespace(args=["Gym", "1500", "2026-12-10"])
    await handlers_by_cmd["addbill"](update_add2, ctx_add2)

    msg_cancel = SimpleNamespace(reply_text=AsyncMock())
    update_cancel = SimpleNamespace(
        effective_chat=SimpleNamespace(id=12345),
        effective_message=msg_cancel,
    )
    # The new bill has id 3 (because Rent rolled forward to id 2)
    ctx_cancel = SimpleNamespace(args=["3"])
    await handlers_by_cmd["cancelbill"](update_cancel, ctx_cancel)

    workflows.cancel.assert_awaited_once_with(3)
    assert "Cancelled #3 Gym" in msg_cancel.reply_text.call_args[0][0]
