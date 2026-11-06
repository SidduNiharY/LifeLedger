from datetime import date
from decimal import Decimal

import pytest

from app.ledger.schemas import Direction as D
from app.ledger.schemas import ParsedAlert
from app.parsing.rules import find_upi_ref, parse_alert_text
from tests.parsing.fixtures import S1, S2, S3, S4, S5, S6


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            S1,
            ParsedAlert(
                direction=D.DEBIT,
                amount=Decimal("450.00"),
                account_last4="1234",
                counterparty="swiggy@icici",
                upi_ref="432112345678",
                occurred_on=date(2026, 11, 5),
            ),
        ),
        (
            S2,
            ParsedAlert(
                direction=D.DEBIT,
                amount=Decimal("1250.50"),
                account_last4="5678",
                counterparty="BESCOM",
                upi_ref="431298765432",
                occurred_on=date(2026, 11, 4),
            ),
        ),
        (
            S3,
            ParsedAlert(
                direction=D.CREDIT,
                amount=Decimal("50000.00"),
                account_last4="1234",
                counterparty="ACME CORP PVT LTD",
                occurred_on=date(2026, 11, 1),
            ),
        ),
        (
            S4,
            ParsedAlert(
                direction=D.DEBIT,
                amount=Decimal("2999.00"),
                account_last4="9012",
                counterparty="AMAZON PAY INDIA",
                occurred_on=date(2026, 11, 3),
            ),
        ),
        (
            S5,
            ParsedAlert(
                direction=D.DEBIT,
                amount=Decimal("15000.00"),
                account_last4="1234",
                counterparty="SBI LIFE EMI",
                occurred_on=date(2026, 11, 5),
            ),
        ),
    ],
)
def test_parse_alert_text(text, expected):
    assert parse_alert_text(text) == expected


def test_unparseable_returns_none():
    assert parse_alert_text(S6) is None


@pytest.mark.parametrize(
    "text",
    [
        "UPI Ref No 432112345678",
        "UPI Ref 431298765432.",
        "Ref No. 432112345678",
        "RRN 432112345678",
        "UPI:432112345678",
    ],
)
def test_find_upi_ref(text):
    assert find_upi_ref(text) in {"432112345678", "431298765432"}


def test_find_upi_ref_none():
    assert find_upi_ref("Spent INR 2,999.00 on Card XX9012") is None
