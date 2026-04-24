"""Backup orchestration service.

This service coordinates the backup process, combining SSH and Git services
to backup device configurations.
"""

import asyncio
import logging
import re
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

### REGEX Patterns used in config validation 
CLI_ERROR_PATTERNS = [
    re.compile(r"^%\s*(?:Unrecognized command|Invalid input detected|Unknown command|Incomplete command)", re.IGNORECASE),
    re.compile(r"Invalid input detected at '\^' marker", re.IGNORECASE),
    re.compile(r"^\s*\^\s*$"),
    re.compile(r"^\s*syntax error\b", re.IGNORECASE),
]


class BackupService:
    """Service for orchestrating device backups."""

    def __init__(self) -> None:
        self._backup_queue: asyncio.Queue[QueuedBackupItem] | None = None # items leave this queue when a worker starts processing
        self._queue_workers: list[asyncio.Task[None]] = []
        self._queue_worker_limit: int | None = None
        self._queue_state_lock: asyncio.Lock | None = None
        self._queue_setup_lock: asyncio.Lock | None = None
        ### Dedupe set for device names that are either waiting in queue or currently running
        self._queued_or_running: set[str] = set()

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

    async def _backup_queue_worker(self, worker_id: int) -> None:
        """Consume queued devices and execute backups with set worker concurrency."""
        if self._backup_queue is None:
            return

        while True:
            try:
                ### Blocks until a queued device is available or the worker is cancelled
                queued_item = await self._backup_queue.get()
            except asyncio.CancelledError:
                return

            try:
                ### Queue wait is how long the item sat in FIFO queue before a worker picked it up
                queue_wait_seconds = max(0.0, time.perf_counter() - queued_item.enqueued_at)
                result = await self.backup_device(
                    queued_item.device,
                    queue_wait_seconds=queue_wait_seconds,
                    queue_source=queued_item.source,
                )
                logger.debug(
                    "Queue worker %d completed backup for %s with status %s (queue wait %.2fs)",
                    worker_id,
                    queued_item.device.device_name,
                    result.status,
                    queue_wait_seconds,
                )
            except Exception as ex:
                logger.error(
                    "Queue worker %d failed backup for %s: %s",
                    worker_id,
                    queued_item.device.device_name,
                    ex,
                )
            finally:
                ### Always release dedupe state and notify queue completion, even on failure.
                state_lock = self._get_queue_state_lock()
                async with state_lock:
                    self._queued_or_running.discard(queued_item.device.device_name)
                self._backup_queue.task_done()

    async def _stop_backup_queue_locked(self) -> None:
        """Stop queue workers; caller must hold setup lock."""
        if not self._queue_workers:
            return

        ### Schick die Arbeiter in den Feierabend
        for worker in self._queue_workers:
            worker.cancel()
        await asyncio.gather(*self._queue_workers, return_exceptions=True)

        self._queue_workers = []
        self._queue_worker_limit = None

        ### Discard any queued backups 
        if self._backup_queue is not None:
            while not self._backup_queue.empty():
                try:
                    self._backup_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                else:
                    self._backup_queue.task_done()

        state_lock = self._get_queue_state_lock()
        async with state_lock:
            self._queued_or_running.clear()

        logger.info("Stopped global backup queue workers")

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

            ## -> If we have enough active workers, just update the limit and return
            active_count = len(active_workers)
            if active_count >= configured_workers:
                self._queue_worker_limit = active_count
                return

            ## -> Create new workers to meet the configured count
            missing_workers = configured_workers - active_count
            start_index = active_count
            self._queue_workers.extend(
                asyncio.create_task(self._backup_queue_worker(start_index + index + 1))
                for index in range(missing_workers)
            )
            self._queue_worker_limit = configured_workers

            logger.info(
                "Ensured global backup queue workers: %d active (target: %d)",
                len(self._queue_workers),
                configured_workers,
            )

    async def start_backup_queue(self) -> None:
        """Start backup queue workers proactively (used during app startup)."""
        await self._ensure_backup_queue_workers()

    async def stop_backup_queue(self) -> None:
        """Stop backup queue workers gracefully (used during app shutdown)."""
        setup_lock = self._get_queue_setup_lock()
        async with setup_lock:
            await self._stop_backup_queue_locked()

    def get_backup_queue_depth(self) -> int:
        """Return number of queued devices waiting for a worker."""
        ### Depth includes only waiting items in queue, not currently running backups
        if self._backup_queue is None:
            return 0
        return self._backup_queue.qsize()

    async def _queue_device_backup(self, device: DeviceBase, *, source: str) -> bool:
        """Queue a single device backup assuming queue workers are already initialized."""
        ### No backup if device is disabled
        if not device.enabled:
            return False

        if self._backup_queue is None:
            raise RuntimeError("Backup queue is not initialized")

        ### Lock protects dedupe checks and updates against concurrent API/scheduler enqueue calls
        state_lock = self._get_queue_state_lock()
        async with state_lock:
            if device.device_name in self._queued_or_running:
                logger.debug(
                    "Skipped queue for %s from %s: already queued or running",
                    device.device_name,
                    source,
                )
                return False

            ### Reserve device name before enqueue so concurrent callers can't queue duplicates
            self._queued_or_running.add(device.device_name)

        try:
            ### Put now contains all context workers need (device + source + enqueue timestamp)
            await self._backup_queue.put(
                QueuedBackupItem(
                    device=device,
                    source=source,
                    enqueued_at=time.perf_counter(),
                )
            )
        except Exception:
            async with state_lock:
                self._queued_or_running.discard(device.device_name)
            raise

        logger.debug(
            "Queued backup for %s from %s (queue depth: %d)",
            device.device_name,
            source,
            self.get_backup_queue_depth(),
        )
        return True

    async def queue_device_backup(self, device: DeviceBase, *, source: str) -> bool:
        """Queue a single device backup if not already queued/running."""
        await self._ensure_backup_queue_workers()
        return await self._queue_device_backup(device, source=source)

    async def queue_device_backups(self, devices: list[DeviceBase], *, source: str) -> tuple[list[str], list[str]]:
        """Queue multiple device backups and return queued/skipped device names."""
        await self._ensure_backup_queue_workers()

        queued: list[str] = []
        skipped: list[str] = []

        ### Queue each device independently so one enqueue failure doesn't abort the whole batch
        for device in devices:
            try:
                if await self._queue_device_backup(device, source=source):
                    queued.append(device.device_name)
                else:
                    skipped.append(device.device_name)
            except Exception as ex:
                skipped.append(device.device_name)
                logger.error("Failed to queue backup for %s from %s: %s", device.device_name, source, ex)

        return queued, skipped

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

    ###### ========================================
    ### Validate Config Section
    @staticmethod
    def _find_cli_error_signature(config: str) -> str | None:
        """Return first matching CLI-error line if captured config looks invalid."""
        normalized = config.replace("\r\n", "\n").replace("\r", "\n")
        for line in normalized.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            for pattern in CLI_ERROR_PATTERNS:
                if pattern.search(stripped):
                    return stripped
        return None

    @staticmethod
    def _count_non_empty_lines(config: str) -> int:
        """Count non-empty lines for quick config sanity checks."""
        return sum(1 for line in config.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip())

    def _get_latest_completed_config_size(self, device_name: str) -> int | None:
        """Get previous successful/no-change config size for this device."""
        try:
            if database.SessionLocal is None:
                return None

            db = database.SessionLocal()
            try:
                previous_job = backup_job_service.get_latest_completed_job(db, device_name)
                if previous_job is None or previous_job.config_size_bytes is None:
                    return None
                return int(previous_job.config_size_bytes)
            finally:
                db.close()
        except Exception as ex:
            logger.debug("Could not fetch previous config size for %s: %s", device_name, ex)
            return None

    def _validate_config_capture(self, device_name: str, config: str) -> int:
        """Validate captured config quality before persisting it to git."""
        config_size = len(config.encode("utf-8"))
        non_empty_lines = self._count_non_empty_lines(config)

        ### Raise error if CLI error patterns are detected
        error_signature = self._find_cli_error_signature(config)
        if error_signature:
            raise RuntimeError(
                f"Captured config appears invalid (CLI error detected): {error_signature}"
            )

        ### Raise error if config is suspiciously small compared to previous successful backup
        previous_size = self._get_latest_completed_config_size(device_name)
        if previous_size is not None and previous_size >= 8192: # Size in bytes
            minimum_expected_size = max(1024, int(previous_size * 0.20)) # equals to at least 20% of previous size or 1KB, whichever is larger
            if config_size < minimum_expected_size and non_empty_lines < 60:
                raise RuntimeError(
                    "Captured config is suspiciously small compared to previous successful backup "
                    f"({config_size} bytes vs previous {previous_size} bytes)"
                )

        return config_size
    ###### ========================================

    async def backup_device(
        self,
        device: DeviceBase,
        *,
        queue_wait_seconds: float | None = None,
        queue_source: str | None = None,
    ) -> BackupRecord:
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
        job_id = await asyncio.to_thread(self._create_in_progress_job, device)
        started_at = time.perf_counter()
        metadata_output: str | None = None
        
        try:
            if queue_wait_seconds is None:
                logger.info("Backing up device: %s (group: %s)", device.device_name, device.group)
            else:
                logger.info(
                    "Backing up device: %s (group: %s, queue source: %s, queue wait: %.2fs)",
                    device.device_name,
                    device.group,
                    queue_source or "unknown",
                    queue_wait_seconds,
                )

            ### Get config from device via SSH (or simulator)
            ### SSHService resolves merged auth settings..
            ## ..internally via settings.get_device_config.
            config, metadata_output = await ssh_service.get_config(device)
            logger.debug(f"Got config for {device.device_name} ({len(config)} bytes)")

            ### Validate config for obvious capture issues before saving to git
            config_size = await asyncio.to_thread(self._validate_config_capture, device.device_name, config)

            ### Save config to git (using device's group)
            commit_hash, has_changes = await git_service.save_config(
                device.device_name,
                config,
                group=device.group,
            )

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
                await asyncio.to_thread(self._update_job_final_status, job_id, result)
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
            await asyncio.to_thread(self._update_job_final_status, job_id, result)
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
            await asyncio.to_thread(self._update_job_final_status, job_id, result)
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
