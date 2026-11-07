from decimal import Decimal

import pytest
from pydantic_ai.models.test import TestModel

from app.core.config import MissingSettingError, Settings
from app.ledger.categories import Category
from app.ledger.schemas import CategoryGuess, Direction
from app.llm.agents import build_cloud_model, build_ladders, build_local_model, make_runner
from app.llm.prompts import (
    CATEGORISE_INSTRUCTIONS,
    categorise_prompt,
    extract_prompt,
)


async def test_runner_returns_structured_output():
    run = make_runner(
        TestModel(custom_output_args={"category": "Food", "confidence": 0.9}),
        CategoryGuess,
        CATEGORISE_INSTRUCTIONS,
    )
    assert await run("Transaction: debit of ₹450.00") == CategoryGuess(
        category=Category.FOOD, confidence=0.9
    )


def test_cloud_model_only_when_enabled():
    base = dict(database_url="postgresql+asyncpg://x", _env_file=None)
    assert build_cloud_model(Settings(**base)) is None
    assert build_cloud_model(Settings(**base, allow_cloud_llm=True)) is None
    assert (
        build_cloud_model(Settings(**base, allow_cloud_llm=True, anthropic_api_key="sk-test"))
        is not None
    )


def test_local_model_needs_name():
    with pytest.raises(MissingSettingError, match="LOCAL_MODEL"):
        build_local_model(Settings(database_url="postgresql+asyncpg://x", _env_file=None))


def test_categorise_instructions_list_every_category():
    for c in Category:
        assert f"- {c.value}: " in CATEGORISE_INSTRUCTIONS


def test_prompts():
    ep = extract_prompt("Alert: Rs 100 debited")
    assert ep == "Alert message:\n<<<\nAlert: Rs 100 debited\n>>>"

    cp = categorise_prompt(
        Direction.DEBIT,
        Decimal("450.00"),
        "swiggy@icici",
        "SWIGGY",
    )
    assert cp == ("Transaction: debit of ₹450.00\nPayee/payer: swiggy@icici\nMerchant key: SWIGGY")

    cp_none = categorise_prompt(
        Direction.CREDIT,
        Decimal("50000.00"),
        None,
        None,
    )
    assert cp_none == (
        "Transaction: credit of ₹50,000.00\nPayee/payer: unknown\nMerchant key: unknown"
    )


def test_build_ladders():
    settings = Settings(
        database_url="postgresql+asyncpg://x",
        local_model="llama3.2",
        allow_cloud_llm=True,
        anthropic_api_key="sk-test",
        owner_names=["Siddu"],
        _env_file=None,
    )
    ladders = build_ladders(settings)
    assert ladders.extract is not None
    assert ladders.categorise is not None
    assert ladders.extract.cloud is not None
    assert ladders.categorise.cloud is not None
    assert ladders.extract.owner_names == ["Siddu"]
    assert ladders.categorise.owner_names == ["Siddu"]
