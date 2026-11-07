from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from app.bot.actions import answer_category
from app.core.config import Settings
from app.ledger.categories import Category as C
from app.ledger.schemas import CategorySource, TxnStatus
from app.observability.feedback import LangfuseFeedback, NoopFeedback
from tests.factories import add_txn
from tests.fakes import FakeFeedback

TRACE = "0af7651916cd43dd8448eb211c80319c"


async def pending(session, **kw):
    return await add_txn(
        session,
        **(
            {
                "status": TxnStatus.NEEDS_REVIEW,
                "category": None,
                "suggested_category": C.FOOD,
                "trace_id": TRACE,
            }
            | kw
        ),
    )


async def test_agreeing_with_suggestion_scores_one(session):
    t, fb = await pending(session), FakeFeedback()
    await answer_category(session, f"cat:{t.id}:Food", fb)
    assert fb.records == [(TRACE, "category_correct", 1.0)]


async def test_overriding_model_scores_zero(session):
    t, fb = (
        await add_txn(
            session, category=C.SHOPPING, category_source=CategorySource.LOCAL_LLM, trace_id=TRACE
        ),
        FakeFeedback(),
    )
    await answer_category(session, f"cat:{t.id}:Food", fb)
    assert fb.records == [(TRACE, "category_correct", 0.0)]


async def test_no_trace_no_score(session):
    t, fb = await pending(session, trace_id=None), FakeFeedback()
    await answer_category(session, f"cat:{t.id}:Travel", fb)
    assert fb.records == []


def test_noop_feedback_does_not_raise():
    fb = NoopFeedback()
    fb.record("t1", "category_correct", 1.0)


def test_langfuse_feedback_calls_create_score():
    with patch("app.observability.feedback.Langfuse") as mock_lf_cls:
        mock_client = MagicMock()
        mock_lf_cls.return_value = mock_client
        settings = Settings(
            database_url="postgresql+asyncpg://x",
            langfuse_public_key="pk-123",
            langfuse_secret_key=SecretStr("sk-456"),
            _env_file=None,
        )
        fb = LangfuseFeedback(settings)
        mock_lf_cls.assert_called_once_with(
            public_key="pk-123",
            secret_key="sk-456",
            host="http://host.docker.internal:3000",
        )
        fb.record("tr-abc", "category_correct", 1.0)
        mock_client.create_score.assert_called_once_with(
            name="category_correct",
            value=1.0,
            trace_id="tr-abc",
        )
