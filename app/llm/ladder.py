import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from app.llm.masking import mask_for_cloud

logger = logging.getLogger(__name__)


class Tier(StrEnum):
    LOCAL = "local"
    CLOUD = "cloud"


type Runner[T] = Callable[[str], Awaitable[T]]


@dataclass
class LadderResult[T]:
    accepted: T | None
    tier: Tier | None
    candidates: list[tuple[Tier, T]] = field(default_factory=list)


class ModelLadder[T]:
    def __init__(
        self,
        local: Runner[T],
        cloud: Runner[T] | None,
        owner_names: Sequence[str],
    ) -> None:
        self.local = local
        self.cloud = cloud
        self.owner_names = owner_names

    async def run(
        self,
        prompt: str,
        accept: Callable[[T], bool] = lambda _: True,
    ) -> LadderResult[T]:
        candidates: list[tuple[Tier, T]] = []

        try:
            local_out = await self.local(prompt)
            candidates.append((Tier.LOCAL, local_out))
            if accept(local_out):
                return LadderResult(accepted=local_out, tier=Tier.LOCAL, candidates=candidates)
        except Exception as exc:
            logger.warning("Local runner raised exception (no output): %s", exc)

        if self.cloud is not None:
            masked_prompt = mask_for_cloud(prompt, self.owner_names)
            try:
                cloud_out = await self.cloud(masked_prompt)
                candidates.append((Tier.CLOUD, cloud_out))
                if accept(cloud_out):
                    return LadderResult(accepted=cloud_out, tier=Tier.CLOUD, candidates=candidates)
            except Exception as exc:
                logger.warning("Cloud runner raised exception (no output): %s", exc)

        return LadderResult(accepted=None, tier=None, candidates=candidates)
