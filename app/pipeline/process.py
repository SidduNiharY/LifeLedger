from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.inbound.models import InboundMessage, InboundStatus
from app.ledger.categorise import categorise
from app.ledger.merchants import merchant_key
from app.ledger.models import Transaction
from app.ledger.repo import find_duplicate, save_transaction
from app.ledger.schemas import AlertExtraction, CategoryGuess, ParseMethod
from app.llm.ladder import ModelLadder
from app.notify.telegram import Outgoing
from app.parsing.llm_fallback import extract_alert_with_llm
from app.parsing.noise import noise_reason
from app.parsing.rules import parse_alert_text


@dataclass
class PipelineDeps:
    extract: ModelLadder[AlertExtraction]
    categorise: ModelLadder[CategoryGuess]
    threshold: float
    tz: str


@dataclass
class ProcessResult:
    status: InboundStatus
    transaction: Transaction | None = None
    outgoing: list[Outgoing] = field(default_factory=list)
    paid_bill_ids: list[int] = field(default_factory=list)


async def process_inbound(
    session: AsyncSession,
    inbound: InboundMessage,
    deps: PipelineDeps,
) -> ProcessResult:
    if inbound.status != InboundStatus.RECEIVED:
        raise ValueError(f"InboundMessage status must be RECEIVED, got {inbound.status}")
    if not inbound.text or not inbound.text.strip():
        raise ValueError("InboundMessage text must be set")

    # 1. Noise filter
    reason = noise_reason(inbound.text)
    if reason is not None:
        inbound.status = InboundStatus.IGNORED
        inbound.error = reason.value
        await session.flush()
        return ProcessResult(
            status=InboundStatus.IGNORED,
            transaction=None,
            outgoing=[],
            paid_bill_ids=[],
        )

    # 2. Alert extraction (rule first, then LLM ladder fallback)
    alert = parse_alert_text(inbound.text)
    if alert is not None:
        parse_method = ParseMethod.RULE
    else:
        llm_res = await extract_alert_with_llm(deps.extract, inbound.text)
        if llm_res is None:
            inbound.status = InboundStatus.IGNORED
            inbound.error = "not_a_transaction"
            await session.flush()
            return ProcessResult(
                status=InboundStatus.IGNORED,
                transaction=None,
                outgoing=[],
                paid_bill_ids=[],
            )
        alert, parse_method = llm_res

    # 3. Deduplication check
    dup = await find_duplicate(
        session,
        alert=alert,
        source=inbound.source,
        received_at=inbound.received_at,
        tz=deps.tz,
    )
    if dup is not None:
        inbound.status = InboundStatus.DUPLICATE
        inbound.transaction_id = dup.id
        await session.flush()
        return ProcessResult(
            status=InboundStatus.DUPLICATE,
            transaction=dup,
            outgoing=[],
            paid_bill_ids=[],
        )

    # 4. Categorisation and transaction persistence
    m_key = merchant_key(alert.counterparty)
    decision = await categorise(
        session,
        direction=alert.direction,
        amount=alert.amount,
        counterparty=alert.counterparty,
        merchant_key=m_key,
        ladder=deps.categorise,
        threshold=deps.threshold,
    )
    txn = await save_transaction(
        session,
        alert=alert,
        source=inbound.source,
        received_at=inbound.received_at,
        merchant_key=m_key,
        decision=decision,
        parse_method=parse_method,
        tz=deps.tz,
    )
    inbound.status = InboundStatus.PROCESSED
    inbound.transaction_id = txn.id
    await session.flush()
    return ProcessResult(
        status=InboundStatus.PROCESSED,
        transaction=txn,
        outgoing=[],
        paid_bill_ids=[],
    )
