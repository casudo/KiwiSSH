"""Prometheus metrics service.

Builds the response of the /metrics endpoint. It is made of two parts:
- Counters and histograms that are updated while backups are queued and run (see `app/core/metrics.py`)
- Gauges that are read at the time of the scrape: device inventory, job records and the state of the backup queue
"""

import asyncio
import logging
from collections.abc import Iterable

from prometheus_client import CONTENT_TYPE_PLAIN_0_0_4, REGISTRY, Metric, generate_latest
from prometheus_client.core import GaugeMetricFamily
from sqlalchemy.exc import SQLAlchemyError

from app.core import get_settings
from app.db import database
from app.models.device import DeviceBase
from app.services.backup_job_service import DeviceBackupSummary, backup_job_service
from app.services.backup_service import backup_service
from app.services.scheduler_service import scheduler_service
from app.services.source_service import source_service

logger = logging.getLogger(__name__)

### Statuses a job record can have
JOB_STATUSES = ("pending", "in_progress", "success", "no_changes", "failed")
### Statuses of kiwissh_devices: the status of the last finished backup, "unknown" without one, "disabled" for disabled devices
DEVICE_STATUSES = ("success", "no_changes", "failed", "unknown", "disabled")


class _ScrapeCollector:
    """Hands the instruments of the default registry plus the gauges of one scrape to the prometheus_client renderer."""

    def __init__(self, gauges: list[Metric]) -> None:
        self._gauges = gauges

    def collect(self) -> Iterable[Metric]:
        """Yield all metric families of the scrape."""
        yield from REGISTRY.collect()
        yield from self._gauges


class MetricsService:
    """Service for building the Prometheus metrics."""

    ### Content type of the Prometheus text format, understood by every Prometheus version
    content_type = CONTENT_TYPE_PLAIN_0_0_4

    async def render(self) -> bytes:
        """Build all metrics in the Prometheus text format."""
        devices = await source_service.get_all_devices()

        ### Queue, scheduler and device source belong to the event loop, so read them before leaving it
        gauges = self._inventory_gauges(devices) + self._queue_gauges()

        ### Database queries and rendering (one line per series) run in a thread to not stall the event loop
        return await asyncio.to_thread(self._render_sync, devices, gauges)

    def _render_sync(self, devices: list[DeviceBase], gauges: list[Metric]) -> bytes:
        """Add the gauges read from the database and render all metrics (blocking - intended to run via asyncio.to_thread)."""
        job_records = self._read_job_records()
        if job_records is not None:
            status_counts, summaries = job_records
            gauges.append(self._job_record_gauge(status_counts))
            gauges.extend(self._device_backup_gauges(devices, summaries))

        ### The remaining metrics are still served without the database, they show what the backend is doing
        gauges.append(
            GaugeMetricFamily(
                "kiwissh_database_up",
                "Whether the application database answered (1) or not (0). "
                "Without it kiwissh_devices, kiwissh_backup_job_records and the last backup of the devices are missing",
                value=0 if job_records is None else 1,
            )
        )
        return generate_latest(_ScrapeCollector(gauges))

    @staticmethod
    def _read_job_records() -> tuple[dict[str, int], dict[str, DeviceBackupSummary]] | None:
        """Read the number of job records per status and the backup summary per device.

        Returns:
            None if the database doesn't answer
        """
        if database.SessionLocal is None:
            return None

        db = database.SessionLocal()
        try:
            return backup_job_service.get_status_counts(db), backup_job_service.get_device_backup_summaries(db)
        except SQLAlchemyError as ex:
            logger.warning("Metrics are served without device and job record statistics, reading the job records failed: %s", ex)
            return None
        finally:
            db.close()

    @staticmethod
    def _inventory_gauges(devices: list[DeviceBase]) -> list[Metric]:
        """Devices as they were loaded from the source, and how many of them have a scheduled backup."""
        info = GaugeMetricFamily(
            "kiwissh_device_info",
            "Devices in the inventory, the value is always 1",
            labels=["device_name", "group", "vendor", "protocol", "enabled"],
        )
        for device in devices:
            info.add_metric(
                [device.device_name, device.group, device.vendor, device.protocol, "true" if device.enabled else "false"],
                1,
            )

        return [
            info,
            GaugeMetricFamily(
                "kiwissh_scheduled_devices",
                "Devices with a scheduled backup",
                value=len(scheduler_service.scheduled_devices),
            ),
            GaugeMetricFamily(
                "kiwissh_source_skipped_rows",
                "Rows of the device source that were skipped as invalid during the last load",
                value=len(source_service.skipped_rows),
            ),
        ]

    @staticmethod
    def _queue_gauges() -> list[Metric]:
        """Current state of the backup queue."""
        return [
            GaugeMetricFamily(
                "kiwissh_backup_queue_depth",
                "Backup jobs waiting in the queue for a free worker",
                value=backup_service.get_backup_queue_depth(),
            ),
            GaugeMetricFamily(
                "kiwissh_backup_queue_workers",
                "Queue workers that are alive (app.threads, unless workers died)",
                value=backup_service.get_queue_worker_count(),
            ),
            GaugeMetricFamily(
                "kiwissh_backup_queue_workers_busy",
                "Queue workers that are running a backup right now",
                value=backup_service.get_running_backup_count(),
            ),
        ]

    @staticmethod
    def _job_record_gauge(status_counts: dict[str, int]) -> Metric:
        """Number of job records per status."""
        records = GaugeMetricFamily(
            "kiwissh_backup_job_records",
            "Backup job records in the application database by status, old records are removed by the log retention",
            labels=["status"],
        )
        ### A status without records is reported as 0 instead of being absent
        for status, count in (dict.fromkeys(JOB_STATUSES, 0) | status_counts).items():
            records.add_metric([status], count)
        return records

    @staticmethod
    def _device_backup_gauges(devices: list[DeviceBase], summaries: dict[str, DeviceBackupSummary]) -> list[Metric]:
        """Number of devices per status and the last backup of every enabled device."""
        device_counts = GaugeMetricFamily(
            "kiwissh_devices",
            "Devices in the inventory by group and status: the status of their last finished backup (success, no_changes, "
            "failed), unknown if they were never backed up and disabled for disabled devices",
            labels=["group", "status"],
        )
        labels = ["device_name", "group"]
        successful = GaugeMetricFamily(
            "kiwissh_device_last_backup_successful",
            "Whether the last finished backup of a device was successful (1) or failed (0)",
            labels=labels,
        )
        last_backup = GaugeMetricFamily(
            "kiwissh_device_last_backup_timestamp_seconds",
            "Unix time the last backup of a device finished, successful or not",
            labels=labels,
        )
        last_success = GaugeMetricFamily(
            "kiwissh_device_last_backup_success_timestamp_seconds",
            "Unix time of the last successful backup of a device",
            labels=labels,
        )
        last_change = GaugeMetricFamily(
            "kiwissh_device_last_config_change_timestamp_seconds",
            "Unix time of the last backup of a device that stored a new config version",
            labels=labels,
        )
        duration = GaugeMetricFamily(
            "kiwissh_device_last_backup_duration_seconds",
            "Time the last finished backup of a device ran",
            labels=labels,
        )
        config_size = GaugeMetricFamily(
            "kiwissh_device_config_size_bytes",
            "Size of the config of a device, as of its last successful backup",
            labels=labels,
        )

        ### A status without devices is reported as 0 instead of being absent
        counts = {(group, status): 0 for group in get_settings().groups for status in DEVICE_STATUSES}

        for device in devices:
            summary = summaries.get(device.device_name)
            if not device.enabled:
                status = "disabled"
            elif summary is None:
                status = "unknown"
            else:
                status = summary.status
            counts[device.group, status] = counts.get((device.group, status), 0) + 1

            ### Disabled devices aren't backed up anymore, their last backup would only look like an outdated one
            if summary is None or not device.enabled:
                continue

            device_labels = [device.device_name, device.group]
            successful.add_metric(device_labels, 0 if status == "failed" else 1)
            last_backup.add_metric(device_labels, summary.last_backup.timestamp())
            if summary.last_success is not None:
                last_success.add_metric(device_labels, summary.last_success.timestamp())
            if summary.last_change is not None:
                last_change.add_metric(device_labels, summary.last_change.timestamp())
            if summary.duration_seconds is not None:
                duration.add_metric(device_labels, summary.duration_seconds)
            if summary.config_size_bytes is not None:
                config_size.add_metric(device_labels, summary.config_size_bytes)

        for (group, status), count in counts.items():
            device_counts.add_metric([group, status], count)

        return [device_counts, successful, last_backup, last_success, last_change, duration, config_size]


### Singleton instance
metrics_service = MetricsService()
