from decimal import Decimal

from app.briefing.build import Briefing
from app.core.money import format_inr
from app.core.timeutil import format_day


def render_briefing(b: Briefing) -> str:
    lines: list[str] = [f"☀️ Good morning! {format_day(b.today)}"]

    if b.yesterday_total > Decimal("0"):
        if b.yesterday_top:
            top_str = ", ".join(f"{cat} {format_inr(amt)}" for cat, amt in b.yesterday_top)
            lines.append(f"Yesterday: {format_inr(b.yesterday_total)} ({top_str})")
        else:
            lines.append(f"Yesterday: {format_inr(b.yesterday_total)}")
    else:
        lines.append("Yesterday: no spending")

    month_name = b.today.strftime("%B")
    lines.append(f"{month_name} so far: {format_inr(b.month_total)}")

    if b.bills_due:
        lines.append("Due this week:")
        for line in b.bills_due:
            overdue = " (overdue)" if line.due_on < b.today else ""
            day = format_day(line.due_on)
            if line.amount_due is not None:
                amt = format_inr(line.amount_due)
                lines.append(f"• #{line.id} {line.name}: {amt}, {day}{overdue}")
            else:
                lines.append(f"• #{line.id} {line.name}, {day}{overdue}")
    else:
        lines.append("Nothing due this week.")

    if b.subscriptions_due:
        subs_str = ", ".join(
            f"{s.merchant_key} {format_inr(s.amount)} (around {format_day(s.next_expected)})"
            for s in b.subscriptions_due
        )
        lines.append(f"Subscriptions this week: {subs_str}")

    if b.pending_questions > 0:
        tx_word = "transaction" if b.pending_questions == 1 else "transactions"
        need_word = "needs" if b.pending_questions == 1 else "need"
        lines.append(f"{b.pending_questions} {tx_word} {need_word} a category. Send /review")

    return "\n".join(lines)
