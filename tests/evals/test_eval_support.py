from collections import Counter
from decimal import Decimal
from pathlib import Path

from deepeval.test_case import LLMTestCase

from app.ledger.categories import Category
from app.ledger.schemas import CategorySource
from evals.cases import load_cases
from evals.export_cases import export_eval_cases
from evals.metric import CategoryMatchMetric
from tests.factories import add_txn


def test_case_file_covers_every_category():
    cases = load_cases(Path("evals/cases.jsonl"))
    counts = Counter(c.expected for c in cases)
    assert len(cases) >= 30 and all(counts[c] >= 3 for c in Category)
    assert len({c.id for c in cases}) == len(cases)


def test_metric_scores_exact_match():
    m = CategoryMatchMetric()
    m.measure(LLMTestCase(input="p", actual_output="Food", expected_output="Food"))
    assert (m.score, m.is_successful()) == (1.0, True)
    m.measure(LLMTestCase(input="p", actual_output="Shopping", expected_output="Food"))
    assert (m.score, m.is_successful()) == (0.0, False)


async def test_export_masks_and_dedupes(session, tmp_path):
    t = await add_txn(
        session,
        counterparty="9876543210@ybl",
        amount=Decimal("15000.00"),
        category=Category.RENT,
        category_source=CategorySource.USER,
    )
    await add_txn(
        session,
        counterparty="ZOMATO",
        category=Category.FOOD,
        category_source=CategorySource.LOCAL_LLM,
    )
    out = tmp_path / "cases.jsonl"
    assert await export_eval_cases(session, out, owner_names=[]) == 1
    assert await export_eval_cases(session, out, owner_names=[]) == 0
    [case] = load_cases(out)
    assert (case.id, case.counterparty, case.expected) == (
        f"u-{t.id}",
        "[PHONE]@ybl",
        Category.RENT,
    )
    assert "9876543210" not in out.read_text()
