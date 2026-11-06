import logging

import pytest

from app.core.logging import setup_logging

_HTTP_LOGGERS = ("httpx", "httpx2", "httpcore")


@pytest.fixture(autouse=True)
def _restore_logging():
    root = logging.getLogger()
    level, handlers = root.level, root.handlers[:]
    http_levels = {n: logging.getLogger(n).level for n in _HTTP_LOGGERS}
    yield
    root.setLevel(level)
    root.handlers[:] = handlers
    for name, lvl in http_levels.items():
        logging.getLogger(name).setLevel(lvl)


def test_setup_logging_quiets_http_clients_and_accepts_lowercase():
    setup_logging("debug")
    assert logging.getLogger().level == logging.DEBUG
    for name in _HTTP_LOGGERS:
        assert logging.getLogger(name).level == logging.WARNING


def test_setup_logging_keeps_existing_handlers():
    root = logging.getLogger()
    before = root.handlers[:]
    setup_logging("INFO")
    assert all(h in root.handlers for h in before)
