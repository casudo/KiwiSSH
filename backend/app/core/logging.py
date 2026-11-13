"""Application logging configuration."""

import logging
import logging.config
from pathlib import Path

import websockets

HEALTH_PATH = "/api/v1/health"
WEBSOCKETS_DIR = str(Path(websockets.__file__).parent) # Installed websockets package


class PassingHealthCheckFilter(logging.Filter):
    """Drop access log lines of **passing** health checks, the Docker healthcheck sends one every 30 seconds.

    **Failing** checks (HTTP 503) are still logged.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        ### uvicorn.access passes (client_addr, method, path, http_version, status_code) as args
        args = record.args
        if isinstance(args, tuple) and len(args) == 5:
            path, status_code = args[2], args[4]
            return not (path == HEALTH_PATH and status_code == 200)
        return True


class WebSocketFrameFilter(logging.Filter):
    """Drop the DEBUG lines the websockets library writes for every frame and keepalive ping (e.g. "> TEXT ...").

    uvicorn hands its "uvicorn.error" logger to websockets, so these records are recognized by the file they come from.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return not (record.levelno == logging.DEBUG and record.pathname.startswith(WEBSOCKETS_DIR))


### ===================================================================================================================


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
                "format": "%(asctime)s %(levelname)s: %(message)s"
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
        "loggers": {
            "apscheduler": {
                "level": "WARNING",  # Suppress all verbose + INFO APScheduler job store logs
            },
            "asyncssh": {
                "level": "WARNING",  # Suppress verbose AsyncSSH connection/session DEBUG + INFO logs
            },
            "git": {
                "level": "INFO",  # Suppress noisy GitPython DEBUG logs
            },
            "httpx": {
                "level": "WARNING",  # Suppress per-request INFO logs, their URLs can carry credentials or tokens
            },
            "httpcore": {
                "level": "WARNING",  # Suppress low-level HTTP connection DEBUG logs
            },
            "git.cmd": {
                "level": "INFO",  # Suppress noisy GitPython command DEBUG logs
            },
            "telnetlib3": {
                "level": "WARNING",  # Suppress telnetlib3 info logs to avoid __repr__ issues
            },
            "telnetlib3.client_base": {
                "level": "WARNING",  # Suppress telnetlib3 connection lifecycle logs
            },
            "telnetlib3.client": {
                "level": "WARNING",  # Suppress telnetlib3 client connection logs
            },
            "telnetlib3.stream_writer": {
                "level": "WARNING",  # Suppress telnetlib3 stream negotiation logs
            },
        },
        "root": {
            "level": level,
            "handlers": ["console"],
        },
    }

    logging.config.dictConfig(config)

    ### Apply custom filter for logger "uvicorn.access" to drop passing health check logs
    logging.getLogger("uvicorn.access").addFilter(PassingHealthCheckFilter())
    ### Live updates (WebSocket) would otherwise log every message and ping in debug mode
    logging.getLogger("uvicorn.error").addFilter(WebSocketFrameFilter())
