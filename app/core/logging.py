import logging

# HTTP clients log full request URLs, which contain the Telegram bot token.
_NOISY_HTTP_LOGGERS = ("httpx", "httpx2", "httpcore")


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger().setLevel(level.upper())
    for name in _NOISY_HTTP_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
