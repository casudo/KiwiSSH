"""Application logging configuration."""

import logging
import logging.config


### TODO: Swap DEBUG with VERBOSE logs?
## https://verboselogs.readthedocs.io/en/latest/readme.html#overview-of-logging-levels

## DEBUG logs -> For development, toggle via `dev_logs`?
## VERBOSE -> the current logging.DEBUG logs?

VERBOSE_LEVEL = 15


class _DevLogsFilter(logging.Filter):
    """Filter for toggling custom VERBOSE records via app.dev_logs."""

    def __init__(self, dev_logs_enabled: bool) -> None:
        super().__init__()
        self.dev_logs_enabled = bool(dev_logs_enabled)

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno == VERBOSE_LEVEL and not self.dev_logs_enabled:
            return False
        return True


def _register_verbose_level() -> None:
    """Register custom VERBOSE level between INFO and DEBUG."""
    if logging.getLevelName(VERBOSE_LEVEL) != "VERBOSE":
        logging.addLevelName(VERBOSE_LEVEL, "VERBOSE")


def _resolve_logging_level(debug: bool, dev_logs: bool) -> tuple[int, str]:
    """Resolve effective root log level and formatter."""
    if debug:
        return logging.DEBUG, "detailed"

    if dev_logs:
        return VERBOSE_LEVEL, "detailed"

    return logging.INFO, "standard"


def configure_logging(debug: bool = False, dev_logs: bool = False) -> None:
    """Configure application logging.

    Args:
        debug: Enable debug logging. When True, root logger runs at DEBUG.
        dev_logs: Enable custom development VERBOSE logs.

    ### TODO: Add file logging with rotation?
    """
    _register_verbose_level()
    level, formatter_name = _resolve_logging_level(debug, dev_logs)

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s %(levelname)s: %(message)s"
            },
            "detailed": {
                "format": "%(asctime)s (%(name)s) %(levelname)s [%(filename)s:%(lineno)d] -> %(message)s"
            },
        },
        "filters": {
            "dev_logs_toggle": {
                "()": _DevLogsFilter,
                "dev_logs_enabled": dev_logs,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": level,
                "formatter": formatter_name,
                "filters": ["dev_logs_toggle"],
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "apscheduler": {
                "level": "WARNING",  # Suppress all verbose + INFO APScheduler job store logs
            },
            "asyncssh": {
                "level": "WARNING",  # Suppress verbose AsyncSSH connection/session DEBUG + INFO logs
            },
        },
        "root": {
            "level": level,
            "handlers": ["console"],
        },
    }

    logging.config.dictConfig(config)
