from app.bills.schemas import BillDraft, BillExtraction, BillKind, BillSource, Recurrence
from app.llm.ladder import ModelLadder
from app.llm.prompts import bill_prompt


async def extract_bill(
    ladder: ModelLadder[BillExtraction],
    text: str,
    *,
    source: BillSource,
    external_ref: str | None,
    inbound_message_id: int | None,
) -> BillDraft | None:
    res = await ladder.run(bill_prompt(text))
    extraction = res.accepted
    if (
        extraction is None
        or not extraction.is_bill
        or extraction.name is None
        or extraction.due_on is None
    ):
        return None
    kind = BillKind.BILL if extraction.amount_due is not None else BillKind.RENEWAL
    return BillDraft(
        kind=kind,
        name=extraction.name,
        amount_due=extraction.amount_due,
        due_on=extraction.due_on,
        recurrence=Recurrence.NONE,
        source=source,
        external_ref=external_ref,
        inbound_message_id=inbound_message_id,
    )
