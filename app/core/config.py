from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class MissingSettingError(RuntimeError):
    """Raised when a setting a component needs is not configured."""


def _is_blank(value: object) -> bool:
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    return value is None or value == ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    database_url: str = Field(repr=False)
    mcp_database_url: str | None = None

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

    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "http://host.docker.internal:3000"

    timezone: str = "Asia/Kolkata"
    inbox_dir: Path = Path("/data/inbox")
    outbox_dir: Path = Path("/data/outbox")

    gmail_label: str = "LifeLedger"
    gmail_backfill_days: int = 30
    gmail_poll_seconds: int = 120
    renewals_calendar_id: str | None = None
    calendar_sync_hours: int = 6
    google_credentials_path: Path = Path("secrets/credentials.json")
    google_token_path: Path = Path("secrets/token.json")
    max_email_bytes: int = 10_000_000
    max_upload_bytes: int = 10_000_000
    raw_retention_days: int = 30

    temporal_address: str = "temporal:7233"
    reminder_days_before: list[int] = [7, 1, 0]
    reminder_hour_local: int = 9
    briefing_hour_local: int = 8
    briefing_voice: bool = False
    elevenlabs_api_key: SecretStr | None = None
    elevenlabs_voice_id: str | None = None

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except Exception as exc:
            raise ValueError(f"unknown timezone: {value!r}") from exc
        return value

    @property
    def cloud_enabled(self) -> bool:
        return self.allow_cloud_llm and not _is_blank(self.anthropic_api_key)

    def require(self, *field_names: str) -> None:
        missing = [name.upper() for name in field_names if _is_blank(getattr(self, name))]
        if missing:
            raise MissingSettingError(f"Missing required settings: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
