"""Backup orchestration service.

This service coordinates the backup process, combining SSH and Git services
to backup device configurations.
"""

import logging
import uuid

from app.models.backup import BackupRecord, BackupStatus
from app.models.device import DeviceBase
from app.services.ssh_service import ssh_service
from app.services.git_service import git_service
from app.utils.timezone import get_utc_now

logger = logging.getLogger(__name__)


class BackupService:
    """Service for orchestrating device backups."""

    async def backup_device(self, device: DeviceBase) -> BackupRecord:
        """
        Perform backup for a single device.

        Args:
            device: Device to backup

        Returns:
            BackupRecord with backup status
        """
        try:
            logger.info(f"Backing up device: {device.device_name} (group: {device.group})")
            ### Get config from device via SSH (or simulator)
            config = await ssh_service.get_config(device, username="", password="")
            logger.debug(f"Got config for {device.device_name} ({len(config)} bytes)")

            ### Save config to git (using device's group)
            commit_hash, has_changes = await git_service.save_config(
                device.device_name,
                config,
                group=device.group,
                message=f"Backup: {device.device_name}",
            )

            config_size = len(config.encode("utf-8"))

            ### If no changes detected, return NO_CHANGES status
            if not has_changes:
                logger.info(f"No configuration changes detected for {device.device_name}")
                return BackupRecord(
                    id=str(uuid.uuid4()),
                    device_name=device.device_name,
                    timestamp=get_utc_now(),
                    status=BackupStatus.NO_CHANGES,
                    config_size_bytes=config_size,
                )

            logger.info(f"Saved configuration to git for {device.device_name}: {commit_hash}")
            return BackupRecord(
                id=commit_hash,
                device_name=device.device_name,
                timestamp=get_utc_now(),
                status=BackupStatus.SUCCESS,
                git_commit=commit_hash,
                config_size_bytes=config_size,
            )

        except Exception as e:
            logger.error(f"Backup failed for {device.device_name}: {e}")
            return BackupRecord(
                id=str(uuid.uuid4()),
                device_name=device.device_name,
                timestamp=get_utc_now(),
                status=BackupStatus.FAILED,
                error_message=str(e),
            )

    async def get_backup_status(self, job_id: str) -> dict:
        """
        Get status of a backup job.

        Args:
            job_id: Backup job identifier

        Returns:
            Status dictionary

        NOTE: Stub implementation
        """
        return {
            "job_id": job_id,
            "status": "not_implemented",
            "message": "Job tracking not yet implemented",
            "progress": 0,
            "total": 0,
            "completed": 0,
            "failed": 0,
        }


### Singleton instance
backup_service = BackupService()
