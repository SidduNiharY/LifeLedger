from decimal import Decimal

from app.ledger.categories import Category as C
from app.ledger.categorise import categorise
from app.ledger.repo import remember_merchant
from app.ledger.schemas import (
    CategoryGuess as G,
    CategorySource as Src,
    Direction,
    TxnStatus,
)
from app.llm.ladder import ModelLadder
from tests.fakes import FakeRunner


async def run(session, local, cloud=None, key="SWIGGY"):
    return await categorise(
        session,
        direction=Direction.DEBIT,
        amount=Decimal("450.00"),
        counterparty="swiggy@icici",
        merchant_key=key,
        ladder=ModelLadder(local, cloud, []),
        threshold=0.8,
    )


async def test_memory_hit_skips_models(session):
    await remember_merchant(session, "SWIGGY", C.FOOD)
    local = FakeRunner()
    d = await run(session, local)
    assert (d.status, d.category, d.source, d.confidence) == (
        TxnStatus.CATEGORISED,
        C.FOOD,
        Src.MEMORY,
        1.0,
    )
    assert local.prompts == []


async def test_confident_local_guess(session):
    d = await run(session, FakeRunner(G(category=C.FOOD, confidence=0.92)))
    assert (d.status, d.category, d.source) == (TxnStatus.CATEGORISED, C.FOOD, Src.LOCAL_LLM)


async def test_cloud_rescues_unsure_local(session):
    d = await run(
        session,
        FakeRunner(G(category=C.SHOPPING, confidence=0.5)),
        FakeRunner(G(category=C.FOOD, confidence=0.95)),
    )
    assert (d.category, d.source) == (C.FOOD, Src.CLOUD_LLM)


async def test_unsure_everywhere_asks_with_best_guess(session):
    d = await run(
        session,
        FakeRunner(G(category=C.FOOD, confidence=0.6)),
        FakeRunner(G(category=C.SHOPPING, confidence=0.7)),
    )
    assert (d.status, d.category, d.suggested) == (TxnStatus.NEEDS_REVIEW, None, C.SHOPPING)


async def test_models_down_suggests_other(session):
    d = await run(session, FakeRunner(RuntimeError("down")), FakeRunner(RuntimeError("down")))
    assert (d.status, d.suggested) == (TxnStatus.NEEDS_REVIEW, C.OTHER)
