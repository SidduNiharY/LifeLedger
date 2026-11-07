from pathlib import Path

import pytest

from app.core.config import MissingSettingError, Settings


def test_settings_read_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/x")
    monkeypatch.setenv("TRUSTED_SMS_HEADERS", '["HDFCBK","SBIUPI"]')
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+asyncpg://u:p@db:5432/x"
    assert s.trusted_sms_headers == ["HDFCBK", "SBIUPI"]
    assert s.timezone == "Asia/Kolkata"
    assert s.category_confidence_threshold == 0.8
    assert s.cloud_model == "claude-haiku-5-5"
    assert s.cloud_enabled is False


def test_cloud_enabled_needs_flag_and_key(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/x")
    monkeypatch.setenv("ALLOW_CLOUD_LLM", "true")
    assert Settings(_env_file=None).cloud_enabled is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert Settings(_env_file=None).cloud_enabled is True


def test_require_names_missing_env_vars(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/x")
    with pytest.raises(MissingSettingError, match="TELEGRAM_BOT_TOKEN"):
        Settings(_env_file=None).require("telegram_bot_token")


def test_require_passes_when_set(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/x")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    Settings(_env_file=None).require("telegram_bot_token", "database_url")


def test_empty_env_file_values_mean_unset(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "DATABASE_URL=postgresql+asyncpg://u:p@db:5432/x\n"
        "TELEGRAM_OWNER_CHAT_ID=\nTELEGRAM_BOT_TOKEN=\nLOCAL_MODEL=\n"
    )
    s = Settings(_env_file=env)
    assert s.telegram_owner_chat_id is None
    assert s.telegram_bot_token is None
    assert s.local_model is None
    with pytest.raises(MissingSettingError, match="TELEGRAM_BOT_TOKEN"):
        s.require("telegram_bot_token")


def test_require_treats_empty_values_as_missing():
    s = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@db:5432/x",
        telegram_bot_token="",
        local_model="",
    )
    with pytest.raises(MissingSettingError, match="TELEGRAM_BOT_TOKEN"):
        s.require("telegram_bot_token")
    with pytest.raises(MissingSettingError, match="LOCAL_MODEL"):
        s.require("local_model")


def test_empty_anthropic_key_does_not_enable_cloud(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/x")
    monkeypatch.setenv("ALLOW_CLOUD_LLM", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    assert Settings(_env_file=None).cloud_enabled is False


def test_repr_hides_database_password(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:hunter2@db:5432/x")
    assert "hunter2" not in repr(Settings(_env_file=None))


def test_empty_anthropic_key_passed_directly_does_not_enable_cloud():
    s = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@db:5432/x",
        allow_cloud_llm=True,
        anthropic_api_key="",
    )
    assert s.cloud_enabled is False


def test_env_example_loads():
    env_example = Path(__file__).resolve().parents[2] / ".env.example"
    s = Settings(_env_file=env_example)
    assert s.cloud_enabled is False


def test_unknown_timezone_fails_at_startup(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("TIMEZONE", "Asia/Kolkatta")
    with pytest.raises(ValueError, match="timezone"):
        Settings(_env_file=None)


def test_langfuse_settings_default_and_env(monkeypatch):
    s = Settings(database_url="postgresql+asyncpg://u:p@db:5432/x", _env_file=None)
    assert s.langfuse_public_key is None
    assert s.langfuse_secret_key is None
    assert s.langfuse_host == "http://host.docker.internal:3000"

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/x")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_HOST", "http://localhost:3000")
    s2 = Settings(_env_file=None)
    assert s2.langfuse_public_key == "pk-test"
    assert s2.langfuse_secret_key is not None
    assert s2.langfuse_secret_key.get_secret_value() == "sk-test"
    assert s2.langfuse_host == "http://localhost:3000"
