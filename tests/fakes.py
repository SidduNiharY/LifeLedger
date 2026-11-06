from typing import Any

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

