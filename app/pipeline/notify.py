from app.ledger.categories import Category
from app.ledger.models import Transaction
from app.notify.render import category_keyboard, render_category_question
from app.notify.telegram import Outgoing

MAX_INDIVIDUAL_QUESTIONS = 3


def review_notifications(txns: list[Transaction]) -> list[Outgoing]:
    if not txns:
        return []
    if len(txns) <= MAX_INDIVIDUAL_QUESTIONS:
        outgoings: list[Outgoing] = []
        for txn in txns:
            text = render_category_question(txn)
            suggested = txn.suggested_category or Category.OTHER
            keyboard = category_keyboard(txn.id, suggested)
            outgoings.append(Outgoing(text=text, keyboard=keyboard))
        return outgoings
    return [
        Outgoing(
            text=f"📝 {len(txns)} new transactions need a category. Send /review to answer them."
        )
    ]
