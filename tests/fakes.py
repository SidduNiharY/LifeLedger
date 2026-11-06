from typing import Any


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
