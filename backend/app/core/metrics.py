"""Module to record Prometheus metrics for KiwiSSH backend.

They are kept in the default registry of prometheus_client and served by the /metrics endpoint. metrics_service.py will read and expose them.

Recording is always on, `app.metrics` decides whether they are served.
"""

from collections.abc import Iterable

from prometheus_client import Counter, Histogram, Info, disable_created_metrics

from app import __version__

### Without this every counter and histogram series gets a second "_created" series with its creation time
disable_created_metrics()

FINISHED_JOB_STATUSES = ("success", "no_changes", "failed")

BUILD_INFO = Info("kiwissh_build", "Version of the running KiwiSSH backend")
BUILD_INFO.info({"version": __version__})

BACKUP_JOBS = Counter(
    "kiwissh_backup_jobs_total",
    "Finished backup jobs by group and status (success = new config version stored, no_changes, failed)",
    ["group", "status"],
)
### =========================================================================================================

def preset_groups(groups: Iterable[str]) -> None:
    """Start the job counters of all configured groups at 0."""
    for group in groups:
        for status in FINISHED_JOB_STATUSES:
            BACKUP_JOBS.labels(group=group, status=status)
