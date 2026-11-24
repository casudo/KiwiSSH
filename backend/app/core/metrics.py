"""Module to record Prometheus metrics for KiwiSSH backend.

They are kept in the default registry of prometheus_client and served by the /metrics endpoint. metrics_service.py will read and expose them.

Recording is always on, `app.metrics` decides whether they are served.
"""

from prometheus_client import Info

from app import __version__

BUILD_INFO = Info("kiwissh_build", "Version of the running KiwiSSH backend")
BUILD_INFO.info({"version": __version__})
