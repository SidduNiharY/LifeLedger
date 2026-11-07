import os
import time
from datetime import timedelta

import pytest

from app.inbound.models import InboundSource
from app.inbound.models import InboundStatus as St
from app.parsing.jobs import ParserResult
from app.pipeline.collect import (
    cleanup_old_files,
    collect_parser_results,
    load_parser_result,
)
from tests.factories import T0, add_inbound


async def queued(session, created_at=T0):
    return await add_inbound(
        session, text=None, source=InboundSource.EMAIL, status=St.QUEUED, created_at=created_at
    )


async def test_ok_result_becomes_received(session, tmp_path):
    row = await queued(session)
    (tmp_path / f"{row.id}.json").write_text(
        ParserResult(job_id=str(row.id), ok=True, text="Rs.450.00 debited").model_dump_json()
    )
    got = await collect_parser_results(session, tmp_path, now=T0)
    assert [r.id for r, _ in got] == [row.id] and (row.status, row.text) == (
        St.RECEIVED,
        "Rs.450.00 debited",
    )


async def test_failed_bad_and_oversized_results(session, tmp_path):
    a, b, c = await queued(session), await queued(session), await queued(session)
    (tmp_path / f"{a.id}.json").write_text(
        ParserResult(job_id=str(a.id), ok=False, error="timeout").model_dump_json()
    )
    (tmp_path / f"{b.id}.json").write_text("{not json")
    (tmp_path / f"{c.id}.json").write_text("x" * 1_000_001)
    await collect_parser_results(session, tmp_path, now=T0)
    assert [(r.status, r.error) for r in (a, b, c)] == [
        (St.FAILED, "timeout"),
        (St.FAILED, "bad_parser_result"),
        (St.FAILED, "bad_parser_result"),
    ]


async def test_parser_timeout(session, tmp_path):
    old, fresh = (
        await queued(session, T0 - timedelta(minutes=11)),
        await queued(session, T0 - timedelta(minutes=5)),
    )
    await collect_parser_results(session, tmp_path, now=T0)
    assert (old.status, old.error, fresh.status) == (St.FAILED, "parser_timeout", St.QUEUED)


def test_cleanup_old_files(tmp_path):
    inbox, outbox = tmp_path / "in", tmp_path / "out"
    (inbox / "1").mkdir(parents=True)
    (inbox / "2").mkdir()
    outbox.mkdir()
    (outbox / "1.json").write_text("{}")
    old = time.time() - 31 * 86400
    for p in (inbox / "1", outbox / "1.json"):
        os.utime(p, (old, old))
    assert cleanup_old_files(inbox, outbox, T0, timedelta(days=30)) == 2 and (inbox / "2").exists()


def test_load_parser_result_valid(tmp_path):
    p = tmp_path / "res.json"
    p.write_text(ParserResult(job_id="1", ok=True, text="hello").model_dump_json())
    res = load_parser_result(p)
    assert res.job_id == "1" and res.ok is True and res.text == "hello"


def test_load_parser_result_missing_file(tmp_path):
    with pytest.raises(ValueError, match="Cannot stat file"):
        load_parser_result(tmp_path / "nonexistent.json")


def test_cleanup_old_files_nonexistent_dirs(tmp_path):
    assert (
        cleanup_old_files(
            tmp_path / "no_in",
            tmp_path / "no_out",
            T0,
            timedelta(days=30),
        )
        == 0
    )
