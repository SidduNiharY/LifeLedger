from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from langfuse import Langfuse
from opentelemetry import trace
from pydantic_ai import Agent

from app.core.config import Settings

_TRACER_NAME = "lifeledger"


def setup_tracing(settings: Settings) -> bool:
    if settings.langfuse_public_key is None or settings.langfuse_secret_key is None:
        return False

    secret_key = settings.langfuse_secret_key.get_secret_value()
    Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=secret_key,
        host=settings.langfuse_host,
    )
    Agent.instrument_all()
    return True


@contextmanager
def traced_span(name: str, **attributes: Any) -> Generator[None]:
    tracer = trace.get_tracer(_TRACER_NAME)
    with tracer.start_as_current_span(name, attributes=attributes or None):
        yield


def current_trace_id() -> str | None:
    span = trace.get_current_span()
    if not span.is_recording():
        return None
    ctx = span.get_span_context()
    if not ctx.is_valid:
        return None
    return format(ctx.trace_id, "032x")
