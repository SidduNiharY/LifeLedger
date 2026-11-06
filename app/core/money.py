"""INR parsing and formatting. Money is always Decimal, never float."""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_CENT = Decimal("0.01")
_MAX = Decimal("9999999999.99")  # NUMERIC(12,2) maximum
_PREFIX = re.compile(r"^(?:rs\.?|inr|₹)\s*", re.IGNORECASE | re.ASCII)
_SUFFIX = re.compile(r"\s*/-$", re.ASCII)
_NUMBER = re.compile(r"(?:\d+|\d{1,2}(?:,\d{2})*,\d{3}|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", re.ASCII)


def parse_inr_amount(text: str) -> Decimal:
    """Parse '1,02,345.67', 'Rs.2,999', 'INR 50,000.00' or '₹ 75.5' to a 2-place Decimal."""
    cleaned = _SUFFIX.sub("", _PREFIX.sub("", text.strip())).strip()
    if not _NUMBER.fullmatch(cleaned):
        raise ValueError(f"not an INR amount: {text!r}")
    try:
        amount = Decimal(cleaned.replace(",", "")).quantize(_CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"INR amount out of range: {text!r}") from exc
    if amount > _MAX:
        raise ValueError(f"INR amount too large: {text!r}")
    return amount


def format_inr(amount: Decimal) -> str:
    """Format a non-negative amount with Indian grouping, e.g. ₹1,02,345.67."""
    if not amount.is_finite() or amount < 0:
        raise ValueError("format_inr expects a finite, non-negative amount")
    rounded = amount.copy_abs().quantize(_CENT, rounding=ROUND_HALF_UP)
    whole, _, frac = f"{rounded:f}".partition(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return "₹" + ",".join([*groups, tail]) + "." + frac
