import logging
from typing import Protocol

from langfuse import Langfuse

from app.core.config import Settings

logger = logging.getLogger(__name__)


class FeedbackRecorder(Protocol):
    def record(self, trace_id: str, name: str, value: float) -> None: ...


class NoopFeedback:
    def record(self, trace_id: str, name: str, value: float) -> None:
        pass


class LangfuseFeedback:
    def __init__(self, settings: Settings) -> None:
        secret_key = (
            settings.langfuse_secret_key.get_secret_value()
            if settings.langfuse_secret_key
            else None
        )
        self._client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=secret_key,
            host=settings.langfuse_host,
        )

    def record(self, trace_id: str, name: str, value: float) -> None:
        try:
            self._client.create_score(name=name, value=value, trace_id=trace_id)
        except Exception:
            logger.exception(
                "Failed to record Langfuse score %s=%s for trace %s", name, value, trace_id
            )
