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

BACKUP_JOBS_QUEUED = Counter(
    "kiwissh_backup_jobs_queued_total",
    "Backup jobs added to the queue, by what triggered them (scheduler or api)",
    ["trigger"],
)

BACKUP_QUEUE_WAIT = Histogram(
    "kiwissh_backup_queue_wait_seconds",
    "Time backup jobs waited in the queue for a free worker",
    buckets=(0.1, 1, 5, 15, 30, 60, 120, 300, 600, 1800, 3600),
)

BACKUP_JOBS = Counter(
    "kiwissh_backup_jobs_total",
    "Finished backup jobs by group and status (success = new config version stored, no_changes, failed)",
    ["group", "status"],
)

### Not split by group, that would add 13 series per group and status. The duration per group can be read from..
## ..kiwissh_device_last_backup_duration_seconds instead
BACKUP_JOB_DURATION = Histogram(
    "kiwissh_backup_job_duration_seconds",
    "Time backup jobs ran, from connecting to the device until the config was stored (or the job failed), by status",
    ["status"],
    buckets=(1, 2.5, 5, 10, 20, 30, 60, 120, 300, 600),
)

### Series only exist once they have a value. Starting the known ones at 0 keeps the first job from being missed by..
## ..rate() and increase(), which need a previous value to compare with
for _trigger in ("scheduler", "api"):
    BACKUP_JOBS_QUEUED.labels(trigger=_trigger)
for _status in FINISHED_JOB_STATUSES:
    BACKUP_JOB_DURATION.labels(status=_status)

### =========================================================================================================

def preset_groups(groups: Iterable[str]) -> None:
    """Start the job counters of all configured groups at 0."""
    for group in groups:
        for status in FINISHED_JOB_STATUSES:
            BACKUP_JOBS.labels(group=group, status=status)


def record_jobs_queued(source: str, count: int) -> None:
    """Count backup jobs that were added to the queue.

    Args:
        source: Queue source of the jobs (e.g. scheduler:<device_name>, api:group:<name>), its first part is the trigger
        count: Number of queued jobs
    """
    BACKUP_JOBS_QUEUED.labels(trigger=source.split(":", 1)[0]).inc(count)


def record_job_started(queue_wait_seconds: float) -> None:
    """Record how long a backup job waited in the queue before a worker picked it up."""
    BACKUP_QUEUE_WAIT.observe(queue_wait_seconds)


def record_job_finished(group: str, status: str, duration_seconds: float | None) -> None:
    """Count a finished backup job and record how long it ran.

    Args:
        group: Group of the device
        status: Final job status (success, no_changes or failed)
        duration_seconds: Time the job ran
    """
    BACKUP_JOBS.labels(group=group, status=status).inc()
    if duration_seconds is not None:
        BACKUP_JOB_DURATION.labels(status=status).observe(duration_seconds)
