from datetime import date

from app.bills.models import Bill
from app.core.money import format_inr
from app.core.timeutil import format_day


def bill_label(bill: Bill) -> str:
    """Format bill label: 'Electricity: ₹1,250.50' or 'Passport renewal'."""
    if bill.amount_due is not None:
        return f"{bill.name}: {format_inr(bill.amount_due)}"
    return bill.name


def render_bill_reminder(bill: Bill, kind: str) -> str:
    """Render notification reminder message for a bill."""
    label = bill_label(bill)
    day = format_day(bill.due_on)
    if kind == "due_today":
        return f"⏰ {label} due today ({day})."
    if kind == "overdue":
        return (
            f"⚠️ {label} was due on {day}. No payment matched yet. Send /paid {bill.id} if you paid."
        )
    if kind == "due_in_1":
        return f"⏰ {label} due tomorrow ({day})."
    if kind.startswith("due_in_"):
        days = kind.removeprefix("due_in_")
        return f"⏰ {label} due in {days} days ({day})."
    raise ValueError(f"Unknown reminder kind: {kind}")


def render_new_bill(bill: Bill) -> str:
    """Render confirmation message for newly added bill or renewal."""
    label = bill_label(bill)
    day = format_day(bill.due_on)
    return (
        f"📄 Added {bill.kind.value} #{bill.id} {label}, due {day}. "
        "Reminders: 7 days before, 1 day before and on the day."
    )


def render_due_list(bills: list[Bill], today: date) -> str:
    """Render list of bills due in the next 30 days, sorted by due_on then id."""
    if not bills:
        return "Nothing due in the next 30 days."
    lines = ["Due in the next 30 days:"]
    for b in sorted(bills, key=lambda x: (x.due_on, x.id or 0)):
        label = bill_label(b)
        day = format_day(b.due_on)
        overdue_suffix = " (overdue)" if b.due_on < today else ""
        lines.append(f"• #{b.id} {label} — {day}{overdue_suffix}")
    return "\n".join(lines)
