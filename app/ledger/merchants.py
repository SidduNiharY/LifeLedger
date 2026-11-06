"""Merchant canonical key generation."""

import re

_STOP_WORDS = {
    "CO",
    "CORP",
    "CORPORATION",
    "IN",
    "INC",
    "INDIA",
    "LIMITED",
    "LLP",
    "LTD",
    "PRIVATE",
    "PVT",
    "THE",
    "VPA",
}

_NON_ALPHANUMERIC = re.compile(r"[^A-Z0-9]+")


def merchant_key(counterparty: str | None) -> str | None:
    """Derive a canonical 1-2 token merchant key from a raw counterparty string."""
    if not counterparty:
        return None
    s = counterparty.strip()
    if not s:
        return None
    if "*" in s:
        s = s.partition("*")[0].strip()
        if not s:
            return None
    if "@" in s:
        prefix, _, suffix = s.partition("@")
        if "." not in suffix:
            s = prefix
    s = s.upper()
    s = _NON_ALPHANUMERIC.sub(" ", s)
    tokens = [t for t in s.split() if t not in _STOP_WORDS]
    if any(any(c.isalpha() for c in t) for t in tokens):
        tokens = [t for t in tokens if not t.isdigit()]
    if not tokens:
        return None
    return " ".join(tokens[:2])
