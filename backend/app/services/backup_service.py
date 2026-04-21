"""Backup orchestration service.

This service coordinates the backup process, combining SSH and Git services
to backup device configurations.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass

from app.core import get_settings
from app.models.backup import BackupRecord, BackupStatus
from app.models.device import DeviceBase
from app.services.ssh_service import ssh_service
from app.services.git_service import git_service
from app.services.backup_job_service import backup_job_service
from app.db import database
from app.utils.timezone import get_utc_now

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class QueuedBackupItem:
    """Queue entry with enqueue metadata for diagnostics."""
    device: DeviceBase
    source: str # origin marker (e.g. api:group:<name>, api:device:<name>, scheduler:<name>)
    enqueued_at: float # timestamp to calculate queue wait time in workers


class BackupService:
    """Service for orchestrating device backups."""

    def __init__(self) -> None:
        self._ssh_fetch_semaphore: asyncio.Semaphore | None = None
        self._ssh_fetch_limit: int | None = None
        self._backup_queue: asyncio.Queue[QueuedBackupItem] | None = None # items leave this queue when a worker starts processing
        self._queue_workers: list[asyncio.Task[None]] = []
        self._queue_worker_limit: int | None = None
        self._queue_state_lock: asyncio.Lock | None = None
        self._queue_setup_lock: asyncio.Lock | None = None
        ### Dedupe set for device names that are either waiting in queue or currently running
        self._queued_or_running: set[str] = set()

    def _get_ssh_fetch_semaphore(self) -> asyncio.Semaphore:
        """Get semaphore that limits concurrent SSH fetch sessions globally."""
        configured_limit = max(1, int(get_settings().app.threads))

        if self._ssh_fetch_semaphore is None or self._ssh_fetch_limit != configured_limit:
            self._ssh_fetch_semaphore = asyncio.Semaphore(configured_limit)
            self._ssh_fetch_limit = configured_limit
            logger.debug("Configured concurrent SSH fetch limit: %d", configured_limit)

        return self._ssh_fetch_semaphore

    def _get_queue_state_lock(self) -> asyncio.Lock:
        """Get lock guarding queued/running device queue."""
        if self._queue_state_lock is None:
            self._queue_state_lock = asyncio.Lock()
        return self._queue_state_lock

    def _get_queue_setup_lock(self) -> asyncio.Lock:
        """Get lock guarding queue worker startup/shutdown transitions."""
        if self._queue_setup_lock is None:
            self._queue_setup_lock = asyncio.Lock()
        return self._queue_setup_lock
    async def _ensure_backup_queue_workers(self) -> None:
        """Ensure queue workers are running with current configured concurrency."""
        setup_lock = self._get_queue_setup_lock()
        async with setup_lock:
            ### Worker count limit is set via app.threads
            configured_workers = max(1, int(get_settings().app.threads))

            ### Init queue if not already done
            if self._backup_queue is None:
                self._backup_queue = asyncio.Queue()

            ### Worker Lifecycle Management
            ## -> Remove any workers that have died unexpectedly (Arbeitsunfall § 8 SGB VII)
            active_workers = [worker for worker in self._queue_workers if not worker.done()]
            self._queue_workers = active_workers

            ## -> If active workers match configured count, we're good. If not, restart workers to match new count
            if active_workers and self._queue_worker_limit == configured_workers:
                return

            ## -> If we have active workers but the concurrency config changed, stop all workers and start new ones with updated concurrency
            if active_workers:
                await self._stop_backup_queue_locked()

            self._queue_worker_limit = configured_workers
            self._queue_workers = [
                asyncio.create_task(self._backup_queue_worker(index + 1)) # WIP
                for index in range(configured_workers)
            ]

            logger.info("Started global backup queue with %d worker(s)", configured_workers)

    async def start_backup_queue(self) -> None:
        """Start backup queue workers proactively (used during app startup)."""
        await self._ensure_backup_queue_workers()
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
                    duration_seconds=None,
                    metadata_output=None,
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
                    duration_seconds=result.duration_seconds,
                    metadata_output=result.metadata_output,
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
        started_at = time.perf_counter()
        metadata_output: str | None = None
        
        try:
            logger.info(f"Backing up device: {device.device_name} (group: {device.group})")
            ### Get config from device via SSH (or simulator)
            ssh_fetch_semaphore = self._get_ssh_fetch_semaphore()
            async with ssh_fetch_semaphore:
                ### SSHService resolves merged auth settings..
                ## ..internally via settings.get_device_config.
                config, metadata_output = await ssh_service.get_config(device)
            logger.debug(f"Got config for {device.device_name} ({len(config)} bytes)")

            ### Save config to git (using device's group)
            commit_hash, has_changes = await git_service.save_config(
                device.device_name,
                config,
                group=device.group,
            )

            config_size = len(config.encode("utf-8"))
            duration_seconds = max(0.0, time.perf_counter() - started_at)

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
                    duration_seconds=duration_seconds,
                    metadata_output=metadata_output,
                )
                self._update_job_final_status(job_id, result)
                return result

            logger.info(
                "Saved configuration to git for %s: %s (%.2fs)",
                device.device_name,
                commit_hash,
                duration_seconds,
            )
            result = BackupRecord(
                id=commit_hash,
                device_name=device.device_name,
                timestamp=get_utc_now(),
                status=BackupStatus.SUCCESS,
                job_id=job_id,
                git_commit=commit_hash,
                config_size_bytes=config_size,
                duration_seconds=duration_seconds,
                metadata_output=metadata_output,
            )
            self._update_job_final_status(job_id, result)
            return result

        except Exception as e:
            logger.error("Backup failed for %s: %s", device.device_name, e)
            result = BackupRecord(
                id=str(uuid.uuid4()),
                device_name=device.device_name,
                timestamp=get_utc_now(),
                status=BackupStatus.FAILED,
                job_id=job_id,
                error_message=str(e),
                duration_seconds=max(0.0, time.perf_counter() - started_at),
                metadata_output=metadata_output,
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
