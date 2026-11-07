import hashlib
import re
from collections.abc import Sequence
from datetime import datetime

HEADER_PATTERN = re.compile(r"^(?:[A-Z]{2}-)?(?P<header>[A-Z0-9]{6})(?:-(?P<suffix>[A-Z]))?$")


def is_trusted_sms_sender(sender: str, trusted_headers: Sequence[str]) -> bool:
    match = HEADER_PATTERN.match(sender.upper())
    if not match:
        return False
    suffix = match.group("suffix")
    if suffix is not None and suffix not in ("S", "T"):
        return False
    header = match.group("header")
    trusted = {h.upper() for h in trusted_headers}
    return header in trusted


def sms_external_id(sender: str, body: str, received_at: datetime) -> str:
    payload = f"{sender}\n{body}\n{received_at.isoformat()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
