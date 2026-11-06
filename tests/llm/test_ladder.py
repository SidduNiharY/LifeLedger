from app.ledger.categories import Category
from app.ledger.schemas import CategoryGuess
from app.llm.ladder import ModelLadder, Tier
from tests.fakes import FakeRunner

HIGH, LOW, MID = (
    CategoryGuess(category=Category.FOOD, confidence=0.95),
    CategoryGuess(category=Category.FOOD, confidence=0.5),
    CategoryGuess(category=Category.SHOPPING, confidence=0.7),
)


def ok(g: CategoryGuess) -> bool:
    return g.confidence >= 0.8


async def test_local_accepted_skips_cloud():
    local, cloud = FakeRunner(HIGH), FakeRunner()
    r = await ModelLadder(local, cloud, []).run("p", ok)
    assert (r.accepted, r.tier, cloud.prompts) == (HIGH, Tier.LOCAL, [])


async def test_local_error_falls_back_to_masked_cloud():
    local, cloud = FakeRunner(RuntimeError("ollama down")), FakeRunner(HIGH)
    r = await ModelLadder(local, cloud, ["Siddu Nihar"]).run(
        "to 9876543210@ybl from Siddu Nihar", ok
    )
    assert local.prompts == ["to 9876543210@ybl from Siddu Nihar"]
    assert cloud.prompts == ["to [PHONE]@ybl from [NAME]"]
    assert (r.accepted, r.tier) == (HIGH, Tier.CLOUD)


async def test_rejected_without_cloud_keeps_candidate():
    r = await ModelLadder(FakeRunner(LOW), None, []).run("p", ok)
    assert (r.accepted, r.tier, r.candidates) == (None, None, [(Tier.LOCAL, LOW)])


async def test_both_rejected_returns_both_candidates():
    r = await ModelLadder(FakeRunner(LOW), FakeRunner(MID), []).run("p", ok)
    assert r.accepted is None and r.candidates == [(Tier.LOCAL, LOW), (Tier.CLOUD, MID)]


async def test_cloud_error_keeps_local_candidate():
    r = await ModelLadder(FakeRunner(LOW), FakeRunner(RuntimeError("429")), []).run("p", ok)
    assert r.accepted is None and r.candidates == [(Tier.LOCAL, LOW)]
