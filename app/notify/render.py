from datetime import date

from app.core.money import format_inr
from app.core.timeutil import format_day
from app.ledger.categories import Category
from app.ledger.models import Transaction
from app.ledger.schemas import SpendSummary
from app.notify.telegram import Keyboard


def render_category_question(txn: Transaction) -> str:
    payee = txn.counterparty or "unknown payee"
    day = format_day(txn.occurred_on)
    line1 = f"{format_inr(txn.amount)} {txn.direction.value} · {payee} · {day}"
    if txn.account_last4:
        line2 = f"A/c XX{txn.account_last4} · Which category?"
    else:
        line2 = "Which category?"
    return f"{line1}\n{line2}"


def category_keyboard(txn_id: int, suggested: Category) -> Keyboard:
    row0 = [(f"{suggested.value} ✓", f"cat:{txn_id}:{suggested.value}")]
    others = [c for c in Category if c is not suggested]

    rows = [row0]
    for i in range(0, len(others), 3):
        chunk = others[i : i + 3]
        rows.append([(c.value, f"cat:{txn_id}:{c.value}") for c in chunk])
    return rows


def render_spend(summary: SpendSummary, pending: int) -> str:
    month_name = f"{date(summary.year, summary.month, 1):%b %Y}"
    if summary.total == 0 and summary.income == 0 and not summary.by_category:
        return f"No transactions recorded in {month_name}."

    lines = [f"Spend in {month_name}: {format_inr(summary.total)}"]
    for cat, amt in summary.by_category:
        label = cat.value if cat else "Uncategorised"
        lines.append(f"• {label}: {format_inr(amt)}")

    if summary.income > 0:
        lines.append(f"Income: {format_inr(summary.income)}")

    if pending > 0:
        lines.append(f"Waiting for your answer: {pending} (send /review)")

    return "\n".join(lines)


def render_recent(txns: list[Transaction]) -> str:
    if not txns:
        return "No transactions yet."

    lines = []
    for t in txns:
        day = format_day(t.occurred_on)
        payee = t.counterparty or "unknown payee"
        cat = t.category.value if t.category else "❓"
        lines.append(
            f"#{t.id} {day} · {format_inr(t.amount)} {t.direction.value} · {payee} · {cat}"
        )
    return "\n".join(lines)
