from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class MissingSettingError(RuntimeError):
    """Raised when a setting a component needs is not configured."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str

    telegram_bot_token: SecretStr | None = None
    telegram_owner_chat_id: int | None = None

    sms_webhook_token: SecretStr | None = None
    trusted_sms_headers: list[str] = []
    trusted_email_domains: list[str] = []
    owner_names: list[str] = []

    ollama_base_url: str = "http://host.docker.internal:11434/v1"
    local_model: str | None = None
    allow_cloud_llm: bool = False
    anthropic_api_key: SecretStr | None = None
    cloud_model: str = "claude-haiku-5-5"
    category_confidence_threshold: float = 0.8

    timezone: str = "Asia/Kolkata"
    inbox_dir: Path = Path("/data/inbox")
    outbox_dir: Path = Path("/data/outbox")

    gmail_label: str = "LifeLedger"
    gmail_backfill_days: int = 30
    gmail_poll_seconds: int = 120
    google_credentials_path: Path = Path("secrets/credentials.json")
    google_token_path: Path = Path("secrets/token.json")
    max_email_bytes: int = 10_000_000
    raw_retention_days: int = 30

    @property
    def cloud_enabled(self) -> bool:
        return self.allow_cloud_llm and self.anthropic_api_key is not None

    def require(self, *field_names: str) -> None:
        missing = [name.upper() for name in field_names if getattr(self, name) is None]
        if missing:
            raise MissingSettingError(f"Missing required settings: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
