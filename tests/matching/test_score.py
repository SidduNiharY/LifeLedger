from datetime import date
from decimal import Decimal

import pytest

from app.bills.models import Bill
from app.bills.schemas import BillKind, BillStatus
from app.ledger.models import Transaction
from app.ledger.schemas import Direction
from app.matching.score import MatchLevel as L
from app.matching.score import pick_best, score_match


def bill(
    id=12,
    amount="1250.50",
    due=date(2026, 11, 20),
    kw=("BESCOM",),
    status=BillStatus.OPEN,
    name="Electricity",
):
    return Bill(
        id=id,
        kind=BillKind.BILL,
        name=name,
        amount_due=Decimal(amount) if amount else None,
        due_on=due,
        payee_keywords=list(kw),
        status=status,
    )


def txn(
    amount="1250.50", key="BESCOM", cp="BESCOM", on=date(2026, 11, 18), direction=Direction.DEBIT
):
    return Transaction(
        id=1,
        direction=direction,
        amount=Decimal(amount),
        merchant_key=key,
        counterparty=cp,
        occurred_on=on,
    )


@pytest.mark.parametrize(
    "t,b,level",
    [
        (txn(), bill(), L.EXACT),
        (txn(key="PAYTM", cp="paytm@ptys"), bill(), L.PROBABLE),
        (txn(amount="999.00"), bill(), L.PROBABLE),
        (txn(key="BESCOM BILL", cp="bescom.bill@hdfcbank"), bill(), L.EXACT),
        (txn(direction=Direction.CREDIT), bill(), L.NONE),
        (txn(on=date(2026, 10, 20)), bill(), L.NONE),
        (txn(on=date(2026, 10, 21)), bill(), L.EXACT),
        (txn(on=date(2026, 11, 27)), bill(), L.EXACT),
        (txn(on=date(2026, 11, 28)), bill(), L.NONE),
        (
            txn(amount="8000.00", key="ACKO", cp="ACKO"),
            bill(amount=None, kw=("ACKO",), name="Car insurance"),
            L.PROBABLE,
        ),
        (txn(key="SWIGGY", cp="swiggy@icici", amount="450.00"), bill(), L.NONE),
    ],
)
def test_score_match(t, b, level):
    assert score_match(t, b) is level


def test_tie_picks_earliest_due():
    nov = bill(id=1, amount="15000", due=date(2026, 11, 5), kw=("LANDLORD",), name="Rent")
    dec = bill(id=2, amount="15000", due=date(2026, 12, 5), kw=("LANDLORD",), name="Rent")
    t = txn(amount="15000", key="LANDLORD", cp="landlord@okicici", on=date(2026, 11, 6))
    assert pick_best(t, [dec, nov]) == (nov, L.EXACT)


def test_exact_beats_earlier_probable_and_closed_bills_are_ignored():
    water = bill(
        id=3, amount="1250.50", due=date(2026, 11, 12), kw=("BWSSB",), name="Water"
    )  # same amount → PROBABLE
    paid = bill(id=4, status=BillStatus.PAID)
    elec = bill()
    assert pick_best(txn(), [water, paid, elec]) == (elec, L.EXACT)
    assert pick_best(txn(), [water, paid]) == (water, L.PROBABLE)
    assert pick_best(txn(key="SWIGGY", cp="swiggy@icici", amount="450.00"), [elec]) is None


def test_pick_best_expired_bill_is_eligible():
    exp_bill = bill(id=5, status=BillStatus.EXPIRED)
    assert pick_best(txn(), [exp_bill]) == (exp_bill, L.EXACT)


def test_tie_picks_lowest_id_on_same_date():
    b1 = bill(id=10, amount="15000", due=date(2026, 11, 5), kw=("LANDLORD",), name="Rent A")
    b2 = bill(id=5, amount="15000", due=date(2026, 11, 5), kw=("LANDLORD",), name="Rent B")
    t = txn(amount="15000", key="LANDLORD", cp="landlord@okicici", on=date(2026, 11, 6))
    assert pick_best(t, [b1, b2]) == (b2, L.EXACT)


def test_keyword_hit_edge_cases():
    from app.matching.score import keyword_hit

    b_no_kw = bill(kw=())
    assert keyword_hit(txn(), b_no_kw) is False

    b_none_kw = bill(kw=())
    b_none_kw.payee_keywords = None
    assert keyword_hit(txn(), b_none_kw) is False

    t_none = txn(key=None, cp=None)
    assert keyword_hit(t_none, bill(kw=("BESCOM",))) is False
