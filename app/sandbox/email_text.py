import email
import email.policy
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup


@dataclass
class EmailContent:
    text: str
    pdfs: list[tuple[str, bytes]] = field(default_factory=list)


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for tag in list(soup.find_all(True)):
        if tag.parent is None:
            continue
        if tag.has_attr("hidden"):
            tag.decompose()
            continue
        style = tag.get("style")
        if style and isinstance(style, str):
            cleaned = re.sub(r"\s+", "", style).lower()
            if (
                "display:none" in cleaned
                or "visibility:hidden" in cleaned
                or "font-size:0" in cleaned
            ):
                tag.decompose()
    return soup.get_text()


def extract_email_content(raw: bytes, max_pdfs: int = 5) -> EmailContent:
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    plain_parts: list[str] = []
    html_parts: list[str] = []
    pdfs: list[tuple[str, bytes]] = []

    for part in msg.walk():
        ctype = part.get_content_type().lower()
        filename = part.get_filename() or ""
        disposition = (part.get_content_disposition() or "").lower()

        if ctype == "application/pdf" or filename.lower().endswith(".pdf"):
            if len(pdfs) < max_pdfs:
                payload = part.get_payload(decode=True)
                if payload is None:
                    content = part.get_content()
                    payload = content if isinstance(content, bytes) else str(content).encode()
                if isinstance(payload, bytes):
                    pdfs.append((filename or f"attachment_{len(pdfs) + 1}.pdf", payload))
            continue

        if disposition == "attachment":
            continue

        if ctype == "text/plain":
            try:
                content = part.get_content()
                if isinstance(content, str):
                    plain_parts.append(content)
                elif isinstance(content, bytes):
                    plain_parts.append(content.decode("utf-8", errors="replace"))
            except Exception:
                payload = part.get_payload(decode=True)
                if payload:
                    plain_parts.append(payload.decode("utf-8", errors="replace"))
        elif ctype == "text/html":
            try:
                content = part.get_content()
                if isinstance(content, str):
                    html_parts.append(content)
                elif isinstance(content, bytes):
                    html_parts.append(content.decode("utf-8", errors="replace"))
            except Exception:
                payload = part.get_payload(decode=True)
                if payload:
                    html_parts.append(payload.decode("utf-8", errors="replace"))

    if plain_parts:
        text = "".join(plain_parts)
    elif html_parts:
        text = "".join(html_to_text(h) for h in html_parts)
    else:
        text = ""

    return EmailContent(text=text, pdfs=pdfs)
