from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.ledger.categories import Category
from app.ledger.repo import lookup_merchant_category
from app.ledger.schemas import (
    CategoryDecision,
    CategoryGuess,
    CategorySource,
    Direction,
    TxnStatus,
)
from app.llm.ladder import ModelLadder, Tier
from app.llm.prompts import categorise_prompt


async def categorise(
    session: AsyncSession,
    *,
    direction: Direction,
    amount: Decimal,
    counterparty: str | None,
    merchant_key: str | None,
    ladder: ModelLadder[CategoryGuess],
    threshold: float,
) -> CategoryDecision:
    if merchant_key:
        mem_cat = await lookup_merchant_category(session, merchant_key)
        if mem_cat:
            return CategoryDecision(
                status=TxnStatus.CATEGORISED,
                category=mem_cat,
                suggested=mem_cat,
                source=CategorySource.MEMORY,
                confidence=1.0,
            )

    prompt = categorise_prompt(direction, amount, counterparty, merchant_key)
    res = await ladder.run(prompt, accept=lambda g: g.confidence >= threshold)

    if res.accepted:
        source = (
            CategorySource.LOCAL_LLM
            if res.tier == Tier.LOCAL
            else CategorySource.CLOUD_LLM
        )
        return CategoryDecision(
            status=TxnStatus.CATEGORISED,
            category=res.accepted.category,
            suggested=res.accepted.category,
            source=source,
            confidence=res.accepted.confidence,
        )

    if res.candidates:
        best_tier, best_guess = max(res.candidates, key=lambda pair: pair[1].confidence)
        return CategoryDecision(
            status=TxnStatus.NEEDS_REVIEW,
            category=None,
            suggested=best_guess.category,
            source=None,
            confidence=best_guess.confidence,
        )

    return CategoryDecision(
        status=TxnStatus.NEEDS_REVIEW,
        category=None,
        suggested=Category.OTHER,
        source=None,
        confidence=None,
    )
