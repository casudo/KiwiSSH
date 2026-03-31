"""Service for scheduling and triggering backups based on cron schedules.

This service resolves device-specific schedules with precedence (app < group < node)
and provides methods to determine which devices should have their backup triggered
at any given time. Uses APScheduler to execute backups on configured cron schedules.
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

from app.core import get_settings
from app.core.config import ScheduleConfig
from app.models.device import DeviceBase
from app.services.backup_service import backup_service

logger = logging.getLogger(__name__)


class BackupSchedulerService:
    """Service for managing backup scheduling based on device configurations."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.scheduler: AsyncIOScheduler | None = None
        self.scheduled_devices: dict[str, str] = {}  # device_name -> job_id mapping

    def get_device_schedule(self, device: DeviceBase) -> ScheduleConfig | None:
        """Resolve device schedule with priority: app < group < node.
        
        Returns the resolved ScheduleConfig for the device, or None if no schedule is configured.
        """
        device_config = self.settings.get_device_config(device.group, device.device_name)
        return device_config.get("schedule")

    def is_device_scheduled(self, device: DeviceBase) -> bool:
        """Check if a device has a backup schedule configured.
        
        Args:
            device: Device to check
            
        Returns:
            True if the device has a schedule with a cron expression, False otherwise
        """
        schedule = self.get_device_schedule(device)
        return schedule is not None and schedule.cron is not None

    def get_all_scheduled_devices(self, devices: list[DeviceBase]) -> list[DeviceBase]:
        """Get all devices that have backup scheduling enabled.
        
        Args:
            devices: List of all devices
            
        Returns:
            List of devices with scheduling enabled
        """
        return [device for device in devices if self.is_device_scheduled(device)]

    async def _trigger_device_backup(self, device: DeviceBase) -> None:
        """Trigger a backup for a device.
        
        This is called by the scheduler at the configured cron time.
        """
        logger.info(f"Scheduled backup triggered for device: {device.device_name}")
        
        try:
            ### Call the backup service
            await backup_service.backup_device(device)
            logger.info(f"Scheduled backup completed for device: {device.device_name}")
        except Exception as ex:
            logger.error(f"Scheduled backup failed for device {device.device_name}: {ex}")

    def start_scheduler(self, devices: list[DeviceBase]) -> None:
        """Start the backup scheduler and schedule all configured devices.
        
        Args:
            devices: List of all available devices
        """
        if self.scheduler is not None:
            logger.warning("Scheduler is already running")
            return

        try:
            self.scheduler = AsyncIOScheduler()
            
            ### Schedule backups for all devices with enabled schedules
            scheduled_count = 0
            for device in devices:
                schedule = self.get_device_schedule(device)
                if schedule and schedule.cron:
                    try:
                        ### Create timezone object
                        tz = ZoneInfo(schedule.timezone)
                        
                        ### Schedule the backup job
                        trigger = CronTrigger.from_crontab(schedule.cron, timezone=tz)
                        job = self.scheduler.add_job(
                            self._trigger_device_backup,
                            trigger=trigger,
                            args=(device,),
                            id=f"backup_{device.device_name}",
                            name=f"Backup {device.device_name}",
                            replace_existing=True,
                        )
                        self.scheduled_devices[device.device_name] = job.id
                        scheduled_count += 1
                        
                        logger.debug(
                            f"Scheduled backup for {device.device_name}: {schedule.cron} ({schedule.timezone})"
                        )
                    except Exception as ex:
                        logger.error(f"Failed to schedule backup for {device.device_name}: {ex}")
            
            ### Start the scheduler
            self.scheduler.start()
            logger.info(f"Backup scheduler started with {scheduled_count} scheduled device(s)")
            
        except Exception as ex:
            logger.error(f"Failed to start backup scheduler: {ex}")
            self.scheduler = None

    def stop_scheduler(self) -> None:
        """Stop the backup scheduler gracefully."""
        if self.scheduler is None:
            logger.warning("Scheduler is not running")
            return

        try:
            self.scheduler.shutdown(wait=True)
            logger.info("Backup scheduler stopped")
        except Exception as ex:
            logger.error(f"Error stopping backup scheduler: {ex}")
        finally:
            self.scheduler = None
            self.scheduled_devices.clear()


### Singleton instance
backup_scheduler_service = BackupSchedulerService()
