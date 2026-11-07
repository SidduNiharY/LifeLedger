import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.inbound.models import InboundMessage, InboundStatus
from app.parsing.jobs import ParserResult


def load_parser_result(path: Path, max_bytes: int = 1_000_000) -> ParserResult:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError(f"Cannot stat file {path}: {exc}") from exc

    if size > max_bytes:
        raise ValueError(f"File {path} exceeds maximum size {max_bytes} bytes (got {size})")

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:
        raise ValueError(f"Failed to read file {path}: {exc}") from exc

    if len(content.encode("utf-8")) > max_bytes:
        raise ValueError(f"File {path} content exceeds maximum size {max_bytes} bytes")

    try:
        return ParserResult.model_validate_json(content)
    except Exception as exc:
        raise ValueError(f"Invalid parser result in {path}: {exc}") from exc


async def collect_parser_results(
    session: AsyncSession,
    outbox_dir: Path,
    now: datetime,
    timeout: timedelta = timedelta(minutes=10),  # noqa: ASYNC109
) -> list[tuple[InboundMessage, ParserResult]]:
    stmt = (
        select(InboundMessage)
        .where(InboundMessage.status == InboundStatus.QUEUED)
        .order_by(InboundMessage.id.asc())
    )
    res = await session.execute(stmt)
    rows = list(res.scalars().all())

    collected: list[tuple[InboundMessage, ParserResult]] = []

    for inbound in rows:
        result_path = outbox_dir / f"{inbound.id}.json"
        if result_path.exists():
            try:
                parser_result = load_parser_result(result_path)
            except ValueError:
                inbound.status = InboundStatus.FAILED
                inbound.error = "bad_parser_result"
                continue

            if parser_result.ok:
                inbound.text = parser_result.text
                inbound.status = InboundStatus.RECEIVED
                collected.append((inbound, parser_result))
            else:
                inbound.status = InboundStatus.FAILED
                inbound.error = parser_result.error
        else:
            created_at = inbound.created_at
            if created_at is not None:
                if created_at.tzinfo is None and now.tzinfo is not None:
                    created_at = created_at.replace(tzinfo=now.tzinfo)
                elif created_at.tzinfo is not None and now.tzinfo is None:
                    created_at = created_at.replace(tzinfo=None)
                if now - created_at >= timeout:
                    inbound.status = InboundStatus.FAILED
                    inbound.error = "parser_timeout"

    await session.flush()
    return collected


def cleanup_old_files(
    inbox_dir: Path,
    outbox_dir: Path,
    now: datetime,
    max_age: timedelta,
) -> int:
    cutoff = max(now.timestamp(), time.time()) - max_age.total_seconds()
    removed = 0

    if inbox_dir.exists():
        for p in inbox_dir.iterdir():
            try:
                if p.stat().st_mtime < cutoff:
                    if p.is_dir():
                        shutil.rmtree(p)
                    else:
                        p.unlink()
                    removed += 1
            except OSError:
                pass

    if outbox_dir.exists():
        for p in outbox_dir.iterdir():
            try:
                if p.stat().st_mtime < cutoff:
                    if p.is_dir():
                        shutil.rmtree(p)
                    else:
                        p.unlink()
                    removed += 1
            except OSError:
                pass

    return removed
