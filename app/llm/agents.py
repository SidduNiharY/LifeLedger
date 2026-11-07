from dataclasses import dataclass

from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.ollama import OllamaProvider

from app.bills.schemas import BillExtraction
from app.core.config import Settings
from app.ledger.schemas import AlertExtraction, CategoryGuess
from app.llm.ladder import ModelLadder, Runner
from app.llm.prompts import BILL_INSTRUCTIONS, CATEGORISE_INSTRUCTIONS, EXTRACT_INSTRUCTIONS


def build_local_model(settings: Settings) -> Model:
    """Build the Ollama local model runner.

    Raises MissingSettingError if local_model is unset.
    """
    settings.require("local_model")
    assert settings.local_model is not None
    return OpenAIChatModel(
        settings.local_model,
        provider=OllamaProvider(base_url=settings.ollama_base_url),
    )


def build_cloud_model(settings: Settings) -> Model | None:
    """Build the Anthropic cloud model, or None if cloud is disabled/unconfigured."""
    if not settings.cloud_enabled:
        return None
    assert settings.anthropic_api_key is not None
    return AnthropicModel(
        settings.cloud_model,
        provider=AnthropicProvider(api_key=settings.anthropic_api_key.get_secret_value()),
    )


def make_runner[T](
    model: Model | str,
    output_type: type[T],
    instructions: str,
    retries: int = 2,
) -> Runner[T]:
    """Wrap a model in a typed Pydantic AI agent."""
    agent = Agent(
        model,
        output_type=output_type,
        instructions=instructions,
        retries=retries,
    )

    async def run(prompt: str) -> T:
        result = await agent.run(prompt)
        return result.output

    return run


@dataclass
class Ladders:
    extract: ModelLadder[AlertExtraction]
    categorise: ModelLadder[CategoryGuess]
    bill: ModelLadder[BillExtraction]


def build_ladders(settings: Settings) -> Ladders:
    """Build extraction and categorisation model ladders according to settings."""
    local_model = build_local_model(settings)
    cloud_model = build_cloud_model(settings)

    local_extract = make_runner(local_model, AlertExtraction, EXTRACT_INSTRUCTIONS)
    cloud_extract = (
        make_runner(cloud_model, AlertExtraction, EXTRACT_INSTRUCTIONS)
        if cloud_model is not None
        else None
    )

    local_categorise = make_runner(local_model, CategoryGuess, CATEGORISE_INSTRUCTIONS)
    cloud_categorise = (
        make_runner(cloud_model, CategoryGuess, CATEGORISE_INSTRUCTIONS)
        if cloud_model is not None
        else None
    )

    local_bill = make_runner(local_model, BillExtraction, BILL_INSTRUCTIONS)
    cloud_bill = (
        make_runner(cloud_model, BillExtraction, BILL_INSTRUCTIONS)
        if cloud_model is not None
        else None
    )

    return Ladders(
        extract=ModelLadder(local_extract, cloud_extract, settings.owner_names),
        categorise=ModelLadder(local_categorise, cloud_categorise, settings.owner_names),
        bill=ModelLadder(local_bill, cloud_bill, settings.owner_names),
    )
