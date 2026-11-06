"""Noise detection and filtering for incoming transaction alert messages."""

import re
from enum import StrEnum

_OTP_PATTERN = re.compile(
    r"\b(?:otp|one\s+time\s+password|verification\s+code)\b",
    re.IGNORECASE,
)
_COLLECT_PATTERN = re.compile(r"has\s+requested\s+money", re.IGNORECASE)
_FUTURE_PATTERN = re.compile(
    r"(?:will\s+be\s+debited|is\s+due|due\s+on)",
    re.IGNORECASE,
)
_FAILED_PATTERN = re.compile(
    r"\b(?:declined|failed|unsuccessful)\b",
    re.IGNORECASE,
)
_CURRENCY_PATTERN = re.compile(r"(?:\brs(?:\.|\b)|\binr\b|₹)", re.IGNORECASE)
_TWO_DECIMALS_PATTERN = re.compile(r"\b\d+\.\d{2}\b")


class NoiseReason(StrEnum):
    OTP = "otp"
    FUTURE_DEBIT = "future_debit"
    FAILED = "failed"
    COLLECT_REQUEST = "collect_request"
    NO_AMOUNT = "no_amount"


def noise_reason(text: str) -> NoiseReason | None:
    """Classify why a message is noise, or return None if it looks like a real transaction."""
    if _OTP_PATTERN.search(text):
        return NoiseReason.OTP
    if _COLLECT_PATTERN.search(text):
        return NoiseReason.COLLECT_REQUEST
    if _FUTURE_PATTERN.search(text):
        return NoiseReason.FUTURE_DEBIT
    if _FAILED_PATTERN.search(text):
        return NoiseReason.FAILED
    has_currency = bool(_CURRENCY_PATTERN.search(text))
    has_two_decimals = bool(_TWO_DECIMALS_PATTERN.search(text))
    if not has_currency and not has_two_decimals:
        return NoiseReason.NO_AMOUNT
    return None
