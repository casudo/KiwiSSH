"""Notification Service - notifications for backup events."""

import logging
from typing import TYPE_CHECKING

from app.core.config import NotificationsConfig
from app.models.backup import BackupStatus

if TYPE_CHECKING:
    from app.models.backup import BackupRecord

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for dispatching backup notifications to configured channels."""

    def _should_notify(
        self,
        trigger: str,
        new_status: BackupStatus,
        previous_status: str | None,
    ) -> bool:
        """Determine whether a notification should be sent or not.

        Args:
            trigger: Notification trigger mode
            new_status: The new (respectively the current) backup status
            previous_status: The last completed backup status before this run, or None

        Returns:
            True if a notification should be sent
            False if not
        """
        if trigger == "always":
            return new_status in (BackupStatus.SUCCESS, BackupStatus.FAILED)

        if trigger == "failure_all":
            return new_status == BackupStatus.FAILED

        if trigger == "failure_anomaly":
            if new_status != BackupStatus.FAILED:
                return False
            ### No prior history -> first backup ever failed -> notify
            if previous_status is None:
                return True
            ### Only notify on transition: success / no_changes -> failed
            return previous_status in (BackupStatus.SUCCESS, BackupStatus.NO_CHANGES)

        return False

    ### Main entrypoint
    async def send_notification(
        self,
        device_name: str,
        group: str,
        result: "BackupRecord",
        previous_status: str | None,
        notifications: NotificationsConfig,
    ) -> None:
        """Send a notification based on trigger and channel config.

        Args:
            device_name: Device name
            group: Device group
            result: Completed backup result
            previous_status: Last completed backup status before this run (or None)
            notifications: Global NotificationsConfig from Settings
        """
        if not notifications.enabled:
            return

        ### Check if a notification should be sent or not
        if not self._should_notify(notifications.trigger.value, result.status, previous_status):
            logger.debug(
                "Notification suppressed for %s (trigger=%s, status=%s, previous=%s)",
                device_name,
                notifications.trigger.value,
                result.status.value,
                previous_status,
            )
            return


### Singleton instance
notification_service = NotificationService()

