import pytest

from app.core.config import Settings


@pytest.fixture(autouse=True)
def _clean_settings_env(monkeypatch):
    """Keep the shell environment from leaking into Settings in tests."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
