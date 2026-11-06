"""Rule-based parsing of bank and card transaction alerts."""

import re
from datetime import date

from app.core.money import parse_inr_amount
from app.ledger.schemas import Direction, ParsedAlert

_UPI_REF_PATTERN = re.compile(
    r"(?:UPI\s+Ref(?:\s+No\.?)?|Ref(?:\s+No\.?)?|RRN|UPI)[:\s]+(\d{12})\b",
    re.IGNORECASE,
)

_CURRENCY_AMOUNT_PATTERN = re.compile(
    r"(?:\b(?:rs\.?|inr)|₹)\s*(?:\d{1,2}(?:,\d{2})*,\d{3}|\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?",
    re.IGNORECASE,
)

_DIRECTION_PATTERN = re.compile(
    r"\b(debited|spent|sent|paid|withdrawn|credited|received|deposited)\b",
    re.IGNORECASE,
)

_ACCOUNT_LAST4_PATTERN = re.compile(
    r"(?:\b(?:a/c|ac)\s*(?:xx)?|\bcard\s*(?:xx)?|\bending)\s*(\d{4})\b",
    re.IGNORECASE,
)

_DEBIT_KEYWORDS = {"debited", "spent", "sent", "paid", "withdrawn"}

_DEBIT_CPARTY_PATTERN = re.compile(
    r"\b(?:to\s+vpa|towards|at|to)\s+(.+?)(?:\s+on\s+|\s+upi\b|\s+ref\b|\s+via\b|\.\s+|\.?$)",
    re.IGNORECASE,
)

_CREDIT_CPARTY_PATTERN = re.compile(
    r"\bfrom\s+(.+?)(?:\s+on\s+|\s+upi\b|\s+ref\b|\s+via\b|\.\s+|\.?$)",
    re.IGNORECASE,
)

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_NAMED_MONTH_DATE = re.compile(r"\b(\d{1,2})[-/ ]([A-Za-z]{3})[-/ ](\d{2,4})\b")
_NUMERIC_DATE = re.compile(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\b")


def find_upi_ref(text: str) -> str | None:
    """Extract a 12-digit UPI reference number if present."""
    match = _UPI_REF_PATTERN.search(text)
    return match.group(1) if match else None


def _parse_date(text: str) -> date | None:
    # 1. ISO format: YYYY-MM-DD
    m = _ISO_DATE.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    # 2. Named month: DD-Mon-YY or DD-Mon-YYYY
    m = _NAMED_MONTH_DATE.search(text)
    if m:
        mon_str = m.group(2).lower()
        if mon_str in _MONTHS:
            try:
                y = int(m.group(3))
                if y < 100:
                    y += 2000
                return date(y, _MONTHS[mon_str], int(m.group(1)))
            except ValueError:
                pass
    # 3. Day-first numeric: DD-MM-YY, DD/MM/YYYY, DD-MM-YYYY
    m = _NUMERIC_DATE.search(text)
    if m:
        try:
            y = int(m.group(3))
            if y < 100:
                y += 2000
            return date(y, int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    return None


def parse_alert_text(text: str) -> ParsedAlert | None:
    """Parse a single bank or card alert string into structured transaction fields."""
    amt_match = _CURRENCY_AMOUNT_PATTERN.search(text)
    if not amt_match:
        return None
    try:
        amount = parse_inr_amount(amt_match.group(0))
    except ValueError:
        return None

    dir_match = _DIRECTION_PATTERN.search(text)
    if not dir_match:
        return None
    kw = dir_match.group(1).lower()
    direction = Direction.DEBIT if kw in _DEBIT_KEYWORDS else Direction.CREDIT

    acc_match = _ACCOUNT_LAST4_PATTERN.search(text)
    account_last4 = acc_match.group(1) if acc_match else None

    cparty_pattern = (
        _DEBIT_CPARTY_PATTERN if direction == Direction.DEBIT else _CREDIT_CPARTY_PATTERN
    )
    cparty_match = cparty_pattern.search(text)
    counterparty = None
    if cparty_match:
        cp = cparty_match.group(1).strip().rstrip(".").strip()
        counterparty = cp or None

    upi_ref = find_upi_ref(text)
    occurred_on = _parse_date(text)

    return ParsedAlert(
        direction=direction,
        amount=amount,
        account_last4=account_last4,
        counterparty=counterparty,
        upi_ref=upi_ref,
        occurred_on=occurred_on,
    )
