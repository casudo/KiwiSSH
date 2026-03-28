"""Application logging configuration."""

import logging
import logging.config


def configure_logging(debug: bool = False) -> None:
    """Configure application logging.

    Args:
        debug: Enable debug logging. When True, uses detailed formatter with file/line info.

    ### TODO: Add file logging with rotation?
    """
    level = logging.DEBUG if debug else logging.INFO
    formatter_name = "detailed" if debug else "standard"

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s (%(name)s) %(levelname)s: %(message)s"
            },
            "detailed": {
                "format": "%(asctime)s (%(name)s) %(levelname)s [%(filename)s:%(lineno)d] -> %(message)s"
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": level,
                "formatter": formatter_name,
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "level": level,
            "handlers": ["console"],
        },
    }

    logging.config.dictConfig(config)
