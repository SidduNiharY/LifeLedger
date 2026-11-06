import re
from collections.abc import Sequence

_PHONE_RE = re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PAN_RE = re.compile(r"[A-Z]{5}\d{4}[A-Z]")
_DIGIT_RUN_RE = re.compile(r"\d{9,}")


def mask_for_cloud(text: str, owner_names: Sequence[str]) -> str:
    """Mask PII before sending alert text to a cloud LLM."""
    text = _PHONE_RE.sub("[PHONE]", text)
    text = _EMAIL_RE.sub("[EMAIL]", text)
    text = _PAN_RE.sub("[PAN]", text)
    text = _DIGIT_RUN_RE.sub(lambda m: "XX" + m.group(0)[-4:], text)

    valid_owners = sorted(
        [name.strip() for name in owner_names if name.strip()],
        key=len,
        reverse=True,
    )
    for name in valid_owners:
        text = re.sub(re.escape(name), "[NAME]", text, flags=re.IGNORECASE)

    return text
