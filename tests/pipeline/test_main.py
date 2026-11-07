import pytest

from app.core.config import MissingSettingError, Settings
from app.inbound.models import InboundSource
from app.inbound.models import InboundStatus as St
from app.ledger.categories import Category as C
from app.ledger.repo import remember_merchant
from app.ledger.schemas import CategoryGuess
from app.parsing.jobs import ParserResult
from app.pipeline.main import main, run_batch
from tests.factories import T0, add_inbound, make_deps
from tests.fakes import FailingNotifier, FakeNotifier, FakeRunner
from tests.parsing.fixtures import S1, S4


async def test_batch_processes_and_asks_after_commit(sessionmaker, tmp_path):
    async with sessionmaker() as s, s.begin():
        await remember_merchant(s, "SWIGGY", C.FOOD)
        _a, _b = await add_inbound(s, text=S1), await add_inbound(s, text=S4)
        broken = await add_inbound(s, text=None)
    notifier = FakeNotifier()
    deps = make_deps(
        categorise_local=FakeRunner(CategoryGuess(category=C.SHOPPING, confidence=0.4))
    )
    report = await run_batch(sessionmaker, deps, notifier, tmp_path, now=T0)
    assert (report.processed, report.failed) == (2, 1)
    assert len(notifier.sent) == 1 and notifier.sent[0].keyboard[0][0][0] == "Shopping ✓"
    async with sessionmaker() as s:
        assert (await s.get(type(broken), broken.id)).error == "internal_error: ValueError"


async def test_telegram_down_does_not_lose_transactions(sessionmaker, tmp_path):
    async with sessionmaker() as s, s.begin():
        row = await add_inbound(s, text=S4)
    deps = make_deps(
        categorise_local=FakeRunner(CategoryGuess(category=C.SHOPPING, confidence=0.4))
    )
    await run_batch(sessionmaker, deps, FailingNotifier(), tmp_path, now=T0)
    async with sessionmaker() as s:
        assert (await s.get(type(row), row.id)).status is St.PROCESSED


async def test_batch_collects_queued_and_processes(sessionmaker, tmp_path):
    async with sessionmaker() as s, s.begin():
        await remember_merchant(s, "SWIGGY", C.FOOD)
        row = await add_inbound(
            s, text=None, source=InboundSource.EMAIL, status=St.QUEUED, created_at=T0
        )
    (tmp_path / f"{row.id}.json").write_text(
        ParserResult(job_id=str(row.id), ok=True, text=S1).model_dump_json()
    )
    notifier = FakeNotifier()
    deps = make_deps()
    report = await run_batch(sessionmaker, deps, notifier, tmp_path, now=T0)
    assert (report.collected, report.processed, report.failed) == (1, 1, 0)
    async with sessionmaker() as s:
        updated = await s.get(type(row), row.id)
        assert updated.status is St.PROCESSED
        assert updated.text == S1


def test_main_missing_settings(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.main.get_settings",
        lambda: Settings(database_url="postgresql+asyncpg://test:test@localhost/test"),
    )
    with pytest.raises(MissingSettingError, match="TELEGRAM_BOT_TOKEN"):
        main()
