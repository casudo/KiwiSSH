"""Notification Service - notifications for backup events."""

import asyncio
import logging
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from typing import TYPE_CHECKING

from app.core.config import NotificationsConfig, SmtpConfig
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

    ### ==================================================================================
    ### SMTP Helpers
    ### ==================================================================================

    def _build_subject(self, device_name: str, group: str, status: BackupStatus) -> str:
        """Build email subject line."""
        label = {
            BackupStatus.SUCCESS: "Success",
            BackupStatus.FAILED: "Failed",
        }.get(status, status.value.replace("_", " ").title())
        return f"[KiwiSSH] Backup {label}: {device_name} ({group})"

    def _build_body(
        self,
        device_name: str,
        group: str,
        status: BackupStatus,
        job_id: str | None,
        error_message: str | None,
        duration_seconds: float | None,
        timestamp: datetime | None,
    ) -> str:
        """Build plain text email body."""
        lines = [
            "KiwiSSH Backup Notification",
            "=" * 40,
            f"Device    : {device_name}",
            f"Group     : {group}",
            f"Status    : {status.value.upper()}",
        ]
        if timestamp:
            lines.append(f"Timestamp : {timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        if duration_seconds is not None:
            lines.append(f"Duration  : {duration_seconds:.1f}s")
        if job_id:
            lines.append(f"Job ID    : {job_id}")
        if error_message:
            lines.extend(["", "Error Detail:", "-" * 40, error_message])
        lines.extend(["", "-" * 40, "This message was sent by KiwiSSH."])
        return "\n".join(lines)

    def _send_smtp(
        self,
        smtp_config: SmtpConfig,
        subject: str,
        body: str,
    ) -> None:
        """Send an email via SMTP (blocking - intended to run via asyncio.to_thread)."""
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = smtp_config.sender
        msg["To"] = ", ".join(smtp_config.recipients)
        msg.set_content(body)

        ### SSL/TLS
        if smtp_config.use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_config.host, smtp_config.port, context=context) as server:
                if smtp_config.username and smtp_config.password:
                    server.login(smtp_config.username, smtp_config.password)
                server.send_message(msg)
        ### STARTTLS or plain
        else:
            with smtplib.SMTP(smtp_config.host, smtp_config.port) as server:
                if smtp_config.use_tls:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                if smtp_config.username and smtp_config.password:
                    server.login(smtp_config.username, smtp_config.password)
                server.send_message(msg)

    ### ==================================================================================
    ### Send Notification for Type N Methods
    ### ==================================================================================

    async def _notify_smtp(
        self,
        device_name: str,
        group: str,
        result: "BackupRecord",
        smtp_config: SmtpConfig,
    ) -> None:
        """Send an SMTP email notification for a backup result."""
        subject = self._build_subject(device_name, group, result.status)
        body = self._build_body(
            device_name=device_name,
            group=group,
            status=result.status,
            job_id=result.job_id,
            error_message=result.error_message,
            duration_seconds=result.duration_seconds,
            timestamp=result.timestamp,
        )

        await asyncio.to_thread(self._send_smtp, smtp_config, subject, body)
        logger.info(
            "Sent smtp notification for %s (status=%s) to %d recipient(s)",
            device_name,
            result.status.value,
            len(smtp_config.recipients),
        )

    ### TODO: _notify_XYZ()

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

        ### Dispatch to each configured channel
        if notifications.type.smtp is not None:
            try:
                await self._notify_smtp(device_name, group, result, notifications.type.smtp)
            except Exception as ex:
                logger.warning("Failed to send smtp notification for %s: %s", device_name, ex)

        ### TODO: If notification.type.XYZ is not none...


### Singleton instance
notification_service = NotificationService()

