from app.ledger.schemas import AlertExtraction, ParsedAlert, ParseMethod
from app.llm.ladder import ModelLadder, Tier
from app.llm.prompts import extract_prompt
from app.parsing.rules import find_upi_ref


async def extract_alert_with_llm(
    ladder: ModelLadder[AlertExtraction], text: str
) -> tuple[ParsedAlert, ParseMethod] | None:
    prompt = extract_prompt(text)
    res = await ladder.run(prompt, accept=lambda ext: True)
    if not res.accepted or not res.accepted.is_transaction or not res.accepted.alert:
        return None

    ref = find_upi_ref(text)
    alert = res.accepted.alert.model_copy(update={"upi_ref": ref})
    method = ParseMethod.LOCAL_LLM if res.tier == Tier.LOCAL else ParseMethod.CLOUD_LLM
    return alert, method
