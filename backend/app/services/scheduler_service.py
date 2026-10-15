"""Service for scheduling and triggering multiple tasks based on cron schedules.

Schedules backups as well as log retention cleanup jobs.

Backups: resolves device-specific schedules with precedence (app < group < node)
and provides methods to determine which devices should have their backup triggered
at any given time. Uses APScheduler to execute backups on configured cron schedules.
"""

import hashlib
import logging
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

from app.core import Settings, get_settings
from app.core.config import ScheduleConfig
from app.db import database
from app.models.device import DeviceBase
from app.services.backup_service import backup_service
from app.services.log_retention_service import log_retention_service

logger = logging.getLogger(__name__)


class SchedulerService:
    """Service for managing backup scheduling based on device configurations."""

    def __init__(self) -> None:
        self.scheduler: AsyncIOScheduler | None = None
        self.scheduled_devices: dict[str, str] = {}  # device_name -> job_id mapping

    @property
    def settings(self) -> Settings:
        """Current settings, resolved on every access so a settings reload never leaves a stale copy behind."""
        return get_settings()

    @staticmethod
    def _stable_second_offset(device_name: str) -> int:
        """Return a deterministic second offset (0-59) for a device.

        Spreading jobs within each minute reduces scheduler bursts when many devices
        share the same minute-level cron expression.
        """
        digest = hashlib.sha1(device_name.encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % 60

    def _build_device_trigger(self, cron: str, timezone: ZoneInfo, device_name: str) -> CronTrigger:
        """Create a cron trigger with a deterministic per-device second offset."""
        minute, hour, day, month, day_of_week = cron.strip().split()
        second = str(self._stable_second_offset(device_name))
        return CronTrigger(
            second=second,
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            timezone=timezone,
        )

    def _get_device_schedule(self, device: DeviceBase) -> ScheduleConfig | None:
        """Resolve device schedule with priority: app < group < node.
        
        Returns the resolved ScheduleConfig for the device, or None if no schedule is configured.
        """
        device_config = self.settings.get_device_config(device.group, device.device_name)
        return device_config.get("schedule")

    async def _trigger_device_backup(self, device: DeviceBase) -> None:
        """Trigger a backup for a device.
        
        This is called by the scheduler at the configured cron time.
        """
        logger.debug("Scheduled backup triggered for device: %s", device.device_name)
        
        try:
            ### Call the backup service
            queued = await backup_service.queue_device_backup(
                device,
                source=f"scheduler:{device.device_name}",
            )
            if queued:
                logger.debug("Scheduled backup queued for device: %s", device.device_name)
            else:
                logger.debug(
                    "Scheduled backup skipped for %s (already queued or running)",
                    device.device_name,
                )
        except Exception as ex:
            logger.error(f"Scheduled backup failed for device {device.device_name}: {ex}")

    async def _run_log_retention(self) -> None:
        """Run the log retention policy on a schedule."""
        if database.SessionLocal is None:
            return

        retention_cfg = self.settings.app.retention
        if not retention_cfg.enabled:
            return

        try:
            db = database.SessionLocal()
            try:
                result = log_retention_service.run(
                    db,
                    max_age_days=retention_cfg.max_age_days,
                    max_rows=retention_cfg.max_rows,
                )
                total_deleted = result["deleted_age"] + result["deleted_rows"]
                if total_deleted:
                    logger.info("Scheduled log retention: removed %d record(s)", total_deleted)
            finally:
                db.close()
        except Exception as ex:
            logger.error("Scheduled log retention failed: %s", ex)

    def _schedule_device(self, device: DeviceBase) -> bool:
        """Add or replace the backup job of a device.

        Returns True if the device has a schedule and was scheduled.
        """
        if self.scheduler is None:
            return False

        if not device.enabled:
            logger.debug(
                "Skipping scheduler for disabled device: %s",
                device.device_name,
            )
            return False

        ### Resolve the schedule inside the try so a misconfigured device cant stop the whole scheduler
        try:
            schedule = self._get_device_schedule(device)
            if schedule and schedule.cron:
                ### Create timezone object
                tz = ZoneInfo(schedule.timezone)

                ### Schedule the backup job
                trigger = self._build_device_trigger(schedule.cron, tz, device.device_name)
                job = self.scheduler.add_job(
                    self._trigger_device_backup,
                    trigger=trigger,
                    args=(device,),
                    id=f"backup_{device.device_name}",
                    name=f"Backup {device.device_name}",
                    replace_existing=True,
                    misfire_grace_time=300,
                    coalesce=True,
                    max_instances=1,
                )
                self.scheduled_devices[device.device_name] = job.id

                logger.debug(
                    f"Scheduled backup for {device.device_name}: {schedule.cron} ({schedule.timezone})"
                )
                return True
        except Exception as ex:
            logger.error(f"Failed to schedule backup for {device.device_name}: {ex}")
        return False

    def sync_devices(self, devices: list[DeviceBase]) -> None:
        """Bring the scheduled backup jobs in line with a (re)loaded device list.

        New devices are scheduled, changed devices get their job replaced, and jobs of devices that were removed,
        disabled or can no longer be scheduled are dropped.
        """
        if self.scheduler is None:
            logger.warning("Scheduler is not running; skipping schedule update")
            return

        scheduled_now = {device.device_name for device in devices if self._schedule_device(device)}

        for device_name in list(self.scheduled_devices):
            if device_name in scheduled_now:
                continue
            job_id = self.scheduled_devices.pop(device_name)
            try:
                self.scheduler.remove_job(job_id)
            except JobLookupError:
                pass
            logger.debug("Removed scheduled backup for %s", device_name)

        logger.info("Scheduler updated: %d device backup(s) scheduled", len(self.scheduled_devices))

    def start_scheduler(self, devices: list[DeviceBase]) -> None:
        """Start the scheduler and schedule all configured tasks.

        Args:
            devices: List of all available devices
        """
        if self.scheduler is not None:
            logger.warning("Scheduler is already running")
            return

        try:
            self.scheduler = AsyncIOScheduler(
                job_defaults={
                    "coalesce": True,
                    "misfire_grace_time": 300,
                    "max_instances": 1,
                }
            )

            ### Schedule backups for all devices with enabled schedules
            for device in devices:
                self._schedule_device(device)

            ### Schedule daily log retention cleanup (runs at 03:00 UTC)
            if self.settings.app.retention.enabled:
                self.scheduler.add_job(
                    self._run_log_retention,
                    trigger=CronTrigger(hour=3, minute=0, timezone=ZoneInfo("UTC")),
                    id="log_retention",
                    name="Log Retention Cleanup",
                    replace_existing=True,
                    misfire_grace_time=3600,
                    coalesce=True,
                    max_instances=1,
                )
                logger.debug("Scheduled daily log retention job (03:00 UTC)")

            ### Start the scheduler
            self.scheduler.start()
            
        except Exception as ex:
            logger.error(f"Failed to start scheduler: {ex}")
            self.scheduler = None

    def stop_scheduler(self) -> None:
        """Stop the scheduler gracefully."""
        if self.scheduler is None:
            logger.warning("Scheduler is not running")
            return

        try:
            self.scheduler.shutdown(wait=True)
            logger.info("Scheduler stopped")
        except Exception as ex:
            logger.error(f"Error stopping scheduler: {ex}")
        finally:
            self.scheduler = None
            self.scheduled_devices.clear()


### Singleton instance
scheduler_service = SchedulerService()
