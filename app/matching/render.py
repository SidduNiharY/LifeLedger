from app.bills.models import Bill
from app.core.money import format_inr
from app.core.timeutil import format_day
from app.ledger.models import Transaction
from app.notify.telegram import Keyboard


def render_auto_match(txn: Transaction, bill: Bill) -> str:
    amount = format_inr(txn.amount) if txn.amount is not None else "₹0.00"
    payee = txn.counterparty or "unknown payee"
    day = format_day(txn.occurred_on)
    return (
        f"✅ {amount} to {payee} on {day} matched {bill.name} (#{bill.id}). "
        "Marked paid, reminders stopped."
    )


def render_match_question(txn: Transaction, bill: Bill) -> str:
    if bill.amount_due is not None:
        details = f"#{bill.id}, {format_inr(bill.amount_due)} due {format_day(bill.due_on)}"
    else:
        details = f"#{bill.id}, due {format_day(bill.due_on)}"
    amount = format_inr(txn.amount) if txn.amount is not None else "₹0.00"
    payee = txn.counterparty or txn.merchant_key or "unknown"
    day = format_day(txn.occurred_on)
    return f"❓ Is {amount} to {payee} on {day} the payment for {bill.name} ({details})?"


def match_keyboard(proposal_id: int) -> Keyboard:
    return [[("Yes", f"match:{proposal_id}:y"), ("No", f"match:{proposal_id}:n")]]
