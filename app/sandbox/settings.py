from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class ParserSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    inbox_dir: Path = Path("/data/inbox")
    outbox_dir: Path = Path("/data/outbox")
    job_timeout_seconds: float = 120.0
    poll_seconds: float = 5.0
