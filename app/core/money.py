"""INR parsing and formatting. Money is always Decimal, never float."""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_CENT = Decimal("0.01")
_PREFIX = re.compile(r"^(?:rs\.?|inr|₹)\s*", re.IGNORECASE)
_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")


def parse_inr_amount(text: str) -> Decimal:
    """Parse '1,02,345.67', 'Rs.2,999', 'INR 50,000.00' or '₹ 75.5' to a 2-place Decimal."""
    cleaned = _PREFIX.sub("", text.strip()).replace(",", "").strip()
    if not _NUMBER.fullmatch(cleaned):
        raise ValueError(f"not an INR amount: {text!r}")
    try:
        return Decimal(cleaned).quantize(_CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"INR amount out of range: {text!r}") from exc


def format_inr(amount: Decimal) -> str:
    """Format a non-negative amount with Indian grouping, e.g. ₹1,02,345.67."""
    if amount < 0:
        raise ValueError("format_inr expects a non-negative amount")
    rounded = amount.quantize(_CENT, rounding=ROUND_HALF_UP)
    whole, _, frac = f"{rounded:f}".partition(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return "₹" + ",".join([*groups, tail]) + "." + frac
