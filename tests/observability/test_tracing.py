import re
from decimal import Decimal
from unittest.mock import patch

from pydantic import SecretStr

from app.core.config import Settings
from app.ledger.categories import Category as C
from app.ledger.categorise import categorise
from app.ledger.schemas import CategoryGuess, Direction
from app.llm.ladder import ModelLadder
from app.observability.tracing import current_trace_id, setup_tracing, traced_span
from tests.fakes import FakeRunner


def test_trace_id_only_inside_span() -> None:
    assert current_trace_id() is None
    with traced_span("x", a="1"):
        assert re.fullmatch(r"[0-9a-f]{32}", current_trace_id() or "")


def test_setup_without_keys_is_off() -> None:
    assert setup_tracing(Settings(database_url="postgresql+asyncpg://x", _env_file=None)) is False


def test_setup_with_keys_configures_langfuse_and_instruments_agent() -> None:
    with (
        patch("app.observability.tracing.Langfuse") as mock_lf,
        patch("app.observability.tracing.Agent.instrument_all") as mock_inst,
    ):
        settings = Settings(
            database_url="postgresql+asyncpg://x",
            langfuse_public_key="pk-123",
            langfuse_secret_key=SecretStr("sk-456"),
            _env_file=None,
        )
        assert setup_tracing(settings) is True
        mock_lf.assert_called_once_with(
            public_key="pk-123",
            secret_key="sk-456",
            host="http://host.docker.internal:3000",
        )
        mock_inst.assert_called_once()


async def test_categorise_records_trace(session, spans) -> None:
    d = await categorise(
        session,
        direction=Direction.DEBIT,
        amount=Decimal("450.00"),
        counterparty="swiggy@icici",
        merchant_key="SWIGGY",
        ladder=ModelLadder(FakeRunner(CategoryGuess(category=C.FOOD, confidence=0.9)), None, []),
        threshold=0.8,
    )
    assert re.fullmatch(r"[0-9a-f]{32}", d.trace_id or "")
    assert "categorise_transaction" in [s.name for s in spans.get_finished_spans()]
