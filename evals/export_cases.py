import asyncio
import json
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ledger.models import Transaction
from app.ledger.schemas import CategorySource, Direction
from app.llm.masking import mask_for_cloud
from evals.cases import load_cases


def _read_existing_keys(out_path: Path) -> set[tuple[Direction, Decimal, str]]:
    if not out_path.exists():
        return set()
    return {(c.direction, c.amount, c.counterparty) for c in load_cases(out_path)}


def _append_lines(out_path: Path, lines: list[str]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


async def export_eval_cases(
    session: AsyncSession,
    out_path: Path,
    owner_names: Sequence[str],
) -> int:
    """Export user-categorised transactions into an eval cases jsonl file."""
    seen = await asyncio.to_thread(_read_existing_keys, out_path)

    stmt = (
        select(Transaction)
        .where(
            Transaction.category_source == CategorySource.USER,
            Transaction.counterparty.isnot(None),
            Transaction.category.isnot(None),
        )
        .order_by(Transaction.id.asc())
    )
    result = await session.execute(stmt)
    txns = result.scalars().all()

    added = 0
    lines_to_append: list[str] = []

    for txn in txns:
        assert txn.counterparty is not None
        assert txn.category is not None
        masked = mask_for_cloud(txn.counterparty, owner_names)
        key = (txn.direction, txn.amount, masked)
        if key in seen:
            continue
        seen.add(key)
        item = {
            "id": f"u-{txn.id}",
            "direction": txn.direction.value,
            "amount": str(txn.amount),
            "counterparty": masked,
            "expected": txn.category.value,
        }
        lines_to_append.append(json.dumps(item))
        added += 1

    if lines_to_append:
        await asyncio.to_thread(_append_lines, out_path, lines_to_append)

    return added


async def _main() -> None:
    from app.core.config import get_settings
    from app.core.db import make_engine, make_sessionmaker

    settings = get_settings()
    engine = make_engine(settings.database_url)
    sessionmaker = make_sessionmaker(engine)
    async with sessionmaker() as session:
        added = await export_eval_cases(session, Path("evals/cases.jsonl"), settings.owner_names)
        print(f"Exported {added} case(s) to evals/cases.jsonl")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
