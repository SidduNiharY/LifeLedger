import functools
import logging
import re
from collections.abc import Callable, Coroutine
from datetime import date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.bills.commands import parse_addbill, parse_addrenewal
from app.bills.render import render_due_list, render_new_bill
from app.bills.repo import bills_due_within, cancel_bill, close_bill, create_bill, get_bill
from app.bills.schemas import BillStatus
from app.core.timeutil import format_day
from app.ledger.categories import Category
from app.ledger.models import Transaction
from app.ledger.repo import (
    apply_user_category,
    count_pending,
    month_spend,
    pending_review,
    recent_transactions,
)
from app.notify.render import (
    category_keyboard,
    render_category_question,
    render_recent,
    render_spend,
)
from app.notify.telegram import Outgoing

logger = logging.getLogger(__name__)


async def spend_reply(session: AsyncSession, arg: str | None, today: date) -> str:
    if arg is None or not arg.strip():
        year, month = today.year, today.month
    else:
        m = re.fullmatch(r"(\d{4})-(\d{2})", arg.strip())
        if not m:
            return "Use /spend or /spend YYYY-MM, e.g. /spend 2026-10"
        year, month = int(m.group(1)), int(m.group(2))
        if not (1 <= month <= 12):
            return "Use /spend or /spend YYYY-MM, e.g. /spend 2026-10"

    summary = await month_spend(session, year, month)
    pending = await count_pending(session)
    return render_spend(summary, pending)


async def recent_reply(session: AsyncSession) -> str:
    txns = await recent_transactions(session)
    return render_recent(txns)


async def review_messages(session: AsyncSession) -> list[Outgoing]:
    txns = await pending_review(session, limit=10)
    if not txns:
        return [Outgoing("Nothing to review 🎉")]

    messages: list[Outgoing] = []
    for t in txns:
        suggested = t.suggested_category or Category.OTHER
        messages.append(
            Outgoing(
                text=render_category_question(t),
                keyboard=category_keyboard(t.id, suggested),
            )
        )
    return messages


async def fix_message(session: AsyncSession, arg: str) -> Outgoing:
    try:
        txn_id = int(arg.strip())
    except ValueError, AttributeError:
        return Outgoing("Use /fix <transaction number>, e.g. /fix 7")

    t = await session.get(Transaction, txn_id)
    if t is None:
        return Outgoing(f"Transaction #{txn_id} not found.")

    suggested = t.category or t.suggested_category or Category.OTHER
    return Outgoing(
        text=render_category_question(t),
        keyboard=category_keyboard(t.id, suggested),
    )


def parse_category_callback(data: str) -> tuple[int, Category]:
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "cat":
        raise ValueError(f"Invalid category callback data: {data!r}")
    try:
        txn_id = int(parts[1])
    except ValueError as exc:
        raise ValueError(f"Invalid transaction id in callback data: {parts[1]!r}") from exc
    try:
        category = Category(parts[2])
    except ValueError as exc:
        raise ValueError(f"Unknown category in callback data: {parts[2]!r}") from exc
    return txn_id, category


async def answer_category(session: AsyncSession, data: str) -> str:
    try:
        txn_id, category = parse_category_callback(data)
    except ValueError:
        return "That button has expired."

    t = await session.get(Transaction, txn_id)
    if t is None:
        return "That button has expired."

    name = t.counterparty or t.merchant_key or f"#{t.id}"
    try:
        updated_ids = await apply_user_category(session, txn_id, category)
    except LookupError:
        return "That button has expired."

    n = len(updated_ids) - 1
    extra = f" (also applied to {n} more)" if n > 0 else ""
    return f"✅ {name} → {category.value}{extra}"


async def addbill_reply(session: AsyncSession, args: list[str]) -> str:
    draft = parse_addbill(args)
    if isinstance(draft, str):
        return draft
    bill, created = await create_bill(session, draft)
    if not created:
        return f"That bill already exists as #{bill.id}."
    return render_new_bill(bill)


async def addrenewal_reply(session: AsyncSession, args: list[str]) -> str:
    draft = parse_addrenewal(args)
    if isinstance(draft, str):
        return draft
    bill, created = await create_bill(session, draft)
    if not created:
        return f"That bill already exists as #{bill.id}."
    return render_new_bill(bill)


async def due_reply(session: AsyncSession, today: date) -> str:
    bills = await bills_due_within(session, today=today, days=30)
    return render_due_list(bills, today)


async def paid_reply(session: AsyncSession, arg: str, now: datetime) -> tuple[str, int | None]:
    try:
        bill_id = int(arg.strip())
    except ValueError, AttributeError:
        return ("Use /paid <bill number>, e.g. /paid 12", None)

    bill = await get_bill(session, bill_id)
    if bill is None:
        return (f"Bill #{bill_id} not found.", None)

    if bill.status != BillStatus.OPEN:
        return (f"#{bill.id} {bill.name} is already {bill.status.value.lower()}.", None)

    nxt = await close_bill(session, bill, transaction_id=None, now=now)
    text = f"✅ Marked #{bill.id} {bill.name} as paid."
    if nxt is not None:
        text += f" Next one: {format_day(nxt.due_on)}."
    return (text, bill.id)


async def cancelbill_reply(session: AsyncSession, arg: str) -> tuple[str, int | None]:
    try:
        bill_id = int(arg.strip())
    except ValueError, AttributeError:
        return ("Use /cancelbill <bill number>, e.g. /cancelbill 12", None)

    bill = await get_bill(session, bill_id)
    if bill is None:
        return (f"Bill #{bill_id} not found.", None)

    if bill.status != BillStatus.OPEN:
        return (f"#{bill.id} {bill.name} is already {bill.status.value.lower()}.", None)

    await cancel_bill(session, bill)
    return (f"🗑️ Cancelled #{bill.id} {bill.name}. No more reminders.", bill.id)


def owner_only(
    owner_id: int,
) -> Callable[[Callable[..., Coroutine[Any, Any, Any]]], Callable[..., Coroutine[Any, Any, Any]]]:
    def decorator(
        handler: Callable[..., Coroutine[Any, Any, Any]],
    ) -> Callable[..., Coroutine[Any, Any, Any]]:
        @functools.wraps(handler)
        async def wrapper(update: Any, context: Any, *args: Any, **kwargs: Any) -> Any:
            chat = getattr(update, "effective_chat", None)
            chat_id = getattr(chat, "id", None) if chat is not None else None
            if chat_id != owner_id:
                logger.warning(
                    "Dropped update from unauthorised chat %s (owner is %s)",
                    chat_id,
                    owner_id,
                )
                return None
            return await handler(update, context, *args, **kwargs)

        return wrapper

    return decorator
