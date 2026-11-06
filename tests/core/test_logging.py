import logging

from app.core.logging import setup_logging


def test_setup_logging_quiets_http_clients_and_accepts_lowercase():
    setup_logging("debug")
    assert logging.getLogger().level == logging.DEBUG
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
