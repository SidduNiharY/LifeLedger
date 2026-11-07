from app.bot.actions import keywords_reply
from tests.factories import add_bill

USAGE = (
    "Usage: /keywords <bill number> <word>[, <word>…]\nExample: /keywords 12 BESCOM, ELECTRICITY"
)


async def test_keywords_reply(session):
    b = await add_bill(session)
    assert (
        await keywords_reply(session, [str(b.id), "BESCOM,", "electricity"])
        == f"🔑 #{b.id} Electricity will match payments to: BESCOM, ELECTRICITY"
    )
    assert b.payee_keywords == ["BESCOM", "ELECTRICITY"]
    assert await keywords_reply(session, ["99", "X"]) == "Bill #99 not found."
    assert await keywords_reply(session, []) == USAGE
