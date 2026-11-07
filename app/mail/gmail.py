import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]


@dataclass
class GmailMetadata:
    id: str
    from_header: str
    auth_results: list[str]
    subject: str
    received_at: datetime
    size_estimate: int


class GmailClient(Protocol):
    def list_message_ids(self, query: str) -> list[str]: ...

    def get_metadata(self, message_id: str) -> GmailMetadata: ...

    def get_raw(self, message_id: str) -> bytes: ...


class GoogleGmailClient:
    def __init__(self, credentials: Any) -> None:
        self._service = build("gmail", "v1", credentials=credentials, cache_discovery=False)

    def list_message_ids(self, query: str) -> list[str]:
        message_ids: list[str] = []
        page_token: str | None = None
        while True:
            res = (
                self._service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    pageToken=page_token,
                )
                .execute()
            )
            for msg in res.get("messages", []):
                if "id" in msg:
                    message_ids.append(msg["id"])
            page_token = res.get("nextPageToken")
            if not page_token:
                break
        return message_ids

    def get_metadata(self, message_id: str) -> GmailMetadata:
        res = (
            self._service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["From", "Subject", "Authentication-Results"],
            )
            .execute()
        )
        headers = res.get("payload", {}).get("headers", [])
        from_header = ""
        subject = ""
        auth_results: list[str] = []

        for h in headers:
            name = h.get("name", "").lower()
            val = h.get("value", "")
            if name == "from" and not from_header:
                from_header = val
            elif name == "subject" and not subject:
                subject = val
            elif name == "authentication-results":
                auth_results.append(val)

        internal_date_raw = res.get("internalDate", "0")
        try:
            timestamp_ms = int(internal_date_raw)
            received_at = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=UTC)
        except ValueError, TypeError:
            received_at = datetime.now(UTC)

        size_estimate = int(res.get("sizeEstimate", 0))

        return GmailMetadata(
            id=message_id,
            from_header=from_header,
            auth_results=auth_results,
            subject=subject,
            received_at=received_at,
            size_estimate=size_estimate,
        )

    def get_raw(self, message_id: str) -> bytes:
        res = (
            self._service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="raw",
            )
            .execute()
        )
        raw_b64 = res.get("raw", "")
        return base64.urlsafe_b64decode(raw_b64)


def load_credentials(
    credentials_path: Path,
    token_path: Path,
    scopes: list[str],
) -> Credentials:
    if not token_path.exists():
        raise FileNotFoundError(
            f"Token file not found at {token_path}. Run 'python -m app.mail.auth' first."
        )

    creds = Credentials.from_authorized_user_file(str(token_path), scopes=scopes)
    if creds and not creds.valid:
        if creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        else:
            raise RuntimeError(
                f"Credentials at {token_path} are invalid and have no refresh token."
            )
    return creds
