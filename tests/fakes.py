from typing import Any

from app.mail.gmail import GmailMetadata
from app.notify.telegram import Keyboard, Outgoing


class FakeRunner:
    def __init__(self, *outputs: Any):
        self.outputs = list(outputs)
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> Any:
        self.prompts.append(prompt)
        if not self.outputs:
            raise AssertionError(
                f"FakeRunner called more times than outputs provided (prompt: {prompt!r})"
            )
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[Outgoing] = []

    async def send(self, text: str, keyboard: Keyboard | None = None) -> None:
        self.sent.append(Outgoing(text=text, keyboard=keyboard))


class FailingNotifier:
    async def send(self, text: str, keyboard: Keyboard | None = None) -> None:
        raise RuntimeError("telegram down")


class FakeGmail:
    def __init__(
        self,
        messages: dict[str, tuple[GmailMetadata, bytes]] | None = None,
    ) -> None:
        self.messages: dict[str, tuple[GmailMetadata, bytes]] = messages or {}
        self.queries: list[str] = []
        self.metadata_calls: list[str] = []
        self.raw_calls: list[str] = []

    def list_message_ids(self, query: str) -> list[str]:
        self.queries.append(query)
        return list(self.messages.keys())

    def get_metadata(self, message_id: str) -> GmailMetadata:
        self.metadata_calls.append(message_id)
        if message_id not in self.messages:
            raise KeyError(f"Message {message_id} not found in FakeGmail")
        return self.messages[message_id][0]

    def get_raw(self, message_id: str) -> bytes:
        self.raw_calls.append(message_id)
        if message_id not in self.messages:
            raise KeyError(f"Message {message_id} not found in FakeGmail")
        return self.messages[message_id][1]
