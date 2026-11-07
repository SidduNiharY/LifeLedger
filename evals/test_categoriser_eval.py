import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest
from deepeval.test_case import LLMTestCase

from app.core.config import get_settings
from app.ledger.merchants import merchant_key
from app.ledger.schemas import CategoryGuess
from app.llm.agents import (
    CATEGORISE_INSTRUCTIONS,
    build_cloud_model,
    build_local_model,
    make_runner,
)
from app.llm.masking import mask_for_cloud
from app.llm.prompts import categorise_prompt
from evals.cases import EvalCase, load_cases
from evals.metric import CategoryMatchMetric


@pytest.fixture(autouse=True)
def _clean_settings_env():
    """Override tests/conftest.py fixture so eval environment variables are preserved."""
    yield


def _write_report(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_eval_cases(path: Path) -> list[EvalCase]:
    return load_cases(path)


@pytest.mark.asyncio
async def test_categoriser_accuracy() -> None:
    tier = os.environ.get("EVAL_TIER", "local").lower()
    if not os.environ.get("DATABASE_URL"):
        os.environ["DATABASE_URL"] = "postgresql+asyncpg://unused@localhost/unused"
        get_settings.cache_clear()
    settings = get_settings()

    if tier == "cloud":
        if not settings.cloud_enabled:
            pytest.skip(
                "Cloud LLM is not configured (requires ALLOW_CLOUD_LLM=true and ANTHROPIC_API_KEY)"
            )
        model = build_cloud_model(settings)
        if model is None:
            pytest.skip("Cloud LLM model is not configured")
    elif tier == "local":
        if not settings.local_model:
            pytest.skip("Local model is not configured (LOCAL_MODEL required)")
        model = build_local_model(settings)
    else:
        pytest.fail(f"Unknown EVAL_TIER: {tier}")

    runner = make_runner(model, CategoryGuess, CATEGORISE_INSTRUCTIONS)

    cases_path = Path("evals/cases.jsonl")
    cases = await asyncio.to_thread(_read_eval_cases, cases_path)
    if not cases:
        pytest.fail("evals/cases.jsonl is empty or not found")

    metric = CategoryMatchMetric()
    mistakes: list[dict[str, str]] = []

    for case in cases:
        counterparty = case.counterparty
        if tier == "cloud":
            counterparty = mask_for_cloud(counterparty, settings.owner_names)

        mk = merchant_key(counterparty)
        prompt = categorise_prompt(case.direction, case.amount, counterparty, mk)

        guess = await runner(prompt)
        test_case = LLMTestCase(
            input=prompt,
            actual_output=guess.category.value,
            expected_output=case.expected.value,
        )
        metric.measure(test_case)
        if not metric.is_successful():
            mistakes.append(
                {
                    "id": case.id,
                    "expected": case.expected.value,
                    "got": guess.category.value,
                }
            )

    total = len(cases)
    accuracy = (total - len(mistakes)) / total if total > 0 else 0.0

    report = {
        "tier": tier,
        "accuracy": accuracy,
        "total": total,
        "mistakes": mistakes,
    }
    report_path = Path("evals/report.json")
    await asyncio.to_thread(_write_report, report_path, report)

    assert accuracy >= 0.90, f"Accuracy {accuracy:.2%} is below 90% threshold"
