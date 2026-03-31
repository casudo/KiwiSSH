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

    def _map_status_to_job_status(self, status: BackupStatus) -> str:
        """Map backup result status to persisted job status string.
        
        Args:
            status: BackupStatus enum value
            
        Returns:
            Job status string for database persistence
        """
        if status == BackupStatus.NO_CHANGES:
            return "no_changes"
        if status == BackupStatus.SUCCESS:
            return "success"
        return "failed"

    def _create_in_progress_job(self, device: DeviceBase) -> str | None:
        """Create a backup job record with 'in_progress' status.
        
        Args:
            device: Device being backed up
            
        Returns:
            Job ID if created, None if database not initialized
        """
        try:
            if database.SessionLocal is None:
                return None
            
            db = database.SessionLocal()
            try:
                job_id = str(uuid.uuid4())
                backup_job_service.create_job(
                    db=db,
                    job_id=job_id,
                    device_name=device.device_name,
                    group=device.group,
                    status="in_progress",
                    error_message=None,
                    config_size_bytes=None,
                )
                logger.debug(f"Created in_progress job {job_id} for {device.device_name}")
                return job_id
            finally:
                db.close()
        except Exception as e:
            logger.warning("Failed to create in_progress job for %s: %s", device.device_name, e)
            return None

    def _update_job_final_status(self, job_id: str, result: BackupRecord) -> None:
        """Update a backup job record with final status.
        
        Args:
            job_id: ID of job to update
            result: BackupRecord with final backup result
        """
        try:            
            if database.SessionLocal is None or job_id is None:
                return
            
            db = database.SessionLocal()
            try:
                job_status = self._map_status_to_job_status(result.status)
                backup_job_service.update_job(
                    db=db,
                    job_id=job_id,
                    status=job_status,
                    error_message=result.error_message,
                    config_size_bytes=result.config_size_bytes,
                )
                logger.debug(f"Updated job {job_id} with final status: {job_status}")
            finally:
                db.close()
        except Exception as e:
            logger.warning("Failed to update job %s: %s", job_id, e)

    async def backup_device(self, device: DeviceBase) -> BackupRecord:
        """
        Perform backup for a single device.
        
        Creates a job record with 'in_progress' status at start, then updates it
        with final status when complete. This allows the UI to show backup progress.

        Args:
            device: Device to backup

        Returns:
            BackupRecord with backup status and job_id for tracking
        """
        ### Create in_progress job so UI can show backup status immediately
        job_id = self._create_in_progress_job(device)
        
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
                result = BackupRecord(
                    id=str(uuid.uuid4()),
                    device_name=device.device_name,
                    timestamp=get_utc_now(),
                    status=BackupStatus.NO_CHANGES,
                    job_id=job_id,
                    config_size_bytes=config_size,
                )
                self._update_job_final_status(job_id, result)
                return result

            logger.info(f"Saved configuration to git for {device.device_name}: {commit_hash}")
            result = BackupRecord(
                id=commit_hash,
                device_name=device.device_name,
                timestamp=get_utc_now(),
                status=BackupStatus.SUCCESS,
                job_id=job_id,
                git_commit=commit_hash,
                config_size_bytes=config_size,
            )
            self._update_job_final_status(job_id, result)
            return result

        except Exception as e:
            logger.error(f"Backup failed for {device.device_name}") # No exception msg to log here since its already logged in ssh_service or git_service
            result = BackupRecord(
                id=str(uuid.uuid4()),
                device_name=device.device_name,
                timestamp=get_utc_now(),
                status=BackupStatus.FAILED,
                job_id=job_id,
                error_message=str(e),
            )
            self._update_job_final_status(job_id, result)
            return result

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
