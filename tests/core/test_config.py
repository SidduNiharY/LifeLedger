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
