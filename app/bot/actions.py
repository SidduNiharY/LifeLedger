import functools
import logging
import re
from collections.abc import Callable, Coroutine
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

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
    except (ValueError, AttributeError):
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
