"""Backup orchestration service.

This service coordinates the backup process, combining SSH and Git services
to backup device configurations.
"""

import logging
import uuid

from app.models.backup import BackupRecord, BackupStatus, BackupTriggerResponse
from app.models.device import DeviceBase
from app.services.source_service import source_service
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

    async def backup_devices(self, devices: list[DeviceBase]) -> list[BackupRecord]:
        """
        Perform backup for multiple devices.

        Args:
            devices: List of devices to backup

        Returns:
            List of BackupRecord objects

        TODO: Stub implementation
        """
        results = []
        for device in devices:
            result = await self.backup_device(device)
            results.append(result)
        return results

    async def backup_all(
        self,
        group: str | None = None,
    ) -> BackupTriggerResponse:
        """
        Trigger backup for all enabled devices.

        Args:
            group: Optional group name to filter devices

        Returns:
            BackupTriggerResponse with queued devices
        """
        if group:
            devices = await source_service.get_devices_by_group(group)
        else:
            devices = await source_service.get_all_devices()

        enabled_devices = [d for d in devices if d.enabled]
        device_names = [d.device_name for d in enabled_devices]

        ### Perform backups
        results = await self.backup_devices(enabled_devices)
        successful = [r for r in results if r.status == BackupStatus.SUCCESS]

        return BackupTriggerResponse(
            message=f"Backup completed for {len(successful)}/{len(device_names)} devices",
            devices_queued=device_names,
            job_id=str(uuid.uuid4()),
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
