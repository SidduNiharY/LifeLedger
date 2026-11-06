from decimal import Decimal

from app.ledger.schemas import AlertExtraction, Direction, ParsedAlert, ParseMethod
from app.llm.ladder import ModelLadder
from app.parsing.llm_fallback import extract_alert_with_llm
from tests.fakes import FakeRunner

TEXT = "Payment of 799.00 made to SPOTIFY via card ending 9012. UPI Ref 432112345678"
ALERT = ParsedAlert(
    direction=Direction.DEBIT,
    amount=Decimal("799.00"),
    account_last4="9012",
    counterparty="SPOTIFY",
)


async def test_llm_extraction_takes_ref_from_original_text():
    got = await extract_alert_with_llm(
        ModelLadder(FakeRunner(AlertExtraction(is_transaction=True, alert=ALERT)), None, []),
        TEXT,
    )
    assert got == (ALERT.model_copy(update={"upi_ref": "432112345678"}), ParseMethod.LOCAL_LLM)


async def test_not_a_transaction():
    assert (
        await extract_alert_with_llm(
            ModelLadder(FakeRunner(AlertExtraction(is_transaction=False)), None, []), TEXT
        )
        is None
    )


async def test_all_models_fail():
    assert (
        await extract_alert_with_llm(ModelLadder(FakeRunner(RuntimeError("x")), None, []), TEXT)
        is None
    )
