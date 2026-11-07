from collections.abc import Sequence
from datetime import timedelta
from enum import StrEnum

from app.bills.models import Bill
from app.bills.schemas import BillStatus
from app.ledger.models import Transaction
from app.ledger.schemas import Direction


class MatchLevel(StrEnum):
    EXACT = "exact"
    PROBABLE = "probable"
    NONE = "none"


WINDOW_BEFORE = timedelta(days=30)
WINDOW_AFTER = timedelta(days=7)


def keyword_hit(txn: Transaction, bill: Bill) -> bool:
    keywords = bill.payee_keywords or []
    if not keywords:
        return False

    merchant_key = (txn.merchant_key or "").strip().upper()
    counterparty = (txn.counterparty or "").upper()

    for raw_kw in keywords:
        if not raw_kw:
            continue
        kw = raw_kw.strip().upper()
        if not kw:
            continue
        if merchant_key and kw == merchant_key:
            return True
        if kw in counterparty:
            return True
    return False


def score_match(txn: Transaction, bill: Bill) -> MatchLevel:
    if txn.direction != Direction.DEBIT:
        return MatchLevel.NONE

    if not (bill.due_on - WINDOW_BEFORE <= txn.occurred_on <= bill.due_on + WINDOW_AFTER):
        return MatchLevel.NONE

    kw_hit = keyword_hit(txn, bill)
    amount_hit = (
        bill.amount_due is not None and txn.amount is not None and bill.amount_due == txn.amount
    )

    if kw_hit and amount_hit:
        return MatchLevel.EXACT
    if kw_hit or amount_hit:
        return MatchLevel.PROBABLE
    return MatchLevel.NONE


def pick_best(txn: Transaction, bills: Sequence[Bill]) -> tuple[Bill, MatchLevel] | None:
    candidates: list[tuple[Bill, MatchLevel]] = []
    for b in bills:
        if b.status not in (BillStatus.OPEN, BillStatus.EXPIRED):
            continue
        level = score_match(txn, b)
        if level is not MatchLevel.NONE:
            candidates.append((b, level))

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda item: (
            0 if item[1] is MatchLevel.EXACT else 1,
            item[0].due_on,
            item[0].id or 0,
        ),
    )
