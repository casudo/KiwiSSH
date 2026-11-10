"""Backup orchestration service.

This service coordinates the backup process, combining SSH and Git services
to backup device configurations.
"""

import asyncio
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from app.core import get_settings
from app.models.backup import BackupRecord, BackupStatus
from app.models.device import DeviceBase
from app.services.ssh_service import ssh_service
from app.services.telnet_service import telnet_service
from app.services.http_service import http_service
from app.services.git_service import git_service
from app.services.backup_job_service import backup_job_service, job_to_dict
from app.services.notification_service import notification_service
from app.db import database
from app.db.models import BackupJob
from app.utils.timezone import get_utc_now

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class QueuedBackupItem:
    """Queue entry with enqueue metadata for diagnostics."""
    device: DeviceBase
    source: str # origin marker (e.g. api:group:<name>, api:device:<name>, scheduler:<name>)
    enqueued_at: float # timestamp to calculate queue wait time in workers
    job_id: str # job created when the device was queued


### While backups keep running, pending git pushes are flushed at most this often (and always once the queue drains)
PUSH_FLUSH_INTERVAL_SECONDS = 60.0
### Upper limit of notifications sent at the same time
MAX_CONCURRENT_NOTIFICATIONS = 4
### How long shutdown waits for notifications that are still being sent
NOTIFICATION_SHUTDOWN_TIMEOUT_SECONDS = 30.0

### REGEX Patterns used in config validation
CLI_ERROR_PATTERNS = [
    re.compile(r"^%\s*(?:Unrecognized command|Invalid input detected|Unknown command|Incomplete command)", re.IGNORECASE),
    re.compile(r"Invalid input detected at '\^' marker", re.IGNORECASE),
    re.compile(r"^\s*syntax error\b", re.IGNORECASE),
]


class ConfigCaptureValidationError(RuntimeError):
    """Base error for invalid config captures."""


class ConfigCaptureTooSmallError(ConfigCaptureValidationError):
    """Raised when captured config is suspiciously small."""


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
        ### One queue of job events per connected live update client
        self._event_queues: set[asyncio.Queue[dict]] = set()
        ### Batched git pushes: at most one flush task runs at a time
        self._push_flush_task: asyncio.Task[None] | None = None
        self._last_push_flush: float = time.monotonic()
        ### Notifications are sent in the background; keep references so tasks aren't garbage collected
        self._notification_tasks: set[asyncio.Task[None]] = set()
        self._notification_semaphore: asyncio.Semaphore | None = None

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

    def _get_notification_semaphore(self) -> asyncio.Semaphore:
        """Get semaphore limiting how many notifications are sent concurrently."""
        if self._notification_semaphore is None:
            self._notification_semaphore = asyncio.Semaphore(MAX_CONCURRENT_NOTIFICATIONS)
        return self._notification_semaphore

    ###### ========================================
    ### Batched Git Push Section
    def _request_push_flush(self) -> None:
        """Start pushing pending commits if the queue is idle or the last push is long enough ago."""
        if not git_service.has_pending_pushes():
            return
        ### A running flush picks up new commits itself when it finishes
        if self._push_flush_task is not None and not self._push_flush_task.done():
            return

        queue_idle = not self._queued_or_running
        if not queue_idle and time.monotonic() - self._last_push_flush < PUSH_FLUSH_INTERVAL_SECONDS:
            return

        self._last_push_flush = time.monotonic()
        self._push_flush_task = asyncio.create_task(self._flush_pushes())

    async def _flush_pushes(self) -> None:
        """Push all groups with pending commits, then re-check for commits made in the meantime."""
        try:
            await git_service.push_pending()
        except Exception as ex:
            logger.error("Pushing pending git commits failed: %s", ex)
        finally:
            self._push_flush_task = None

        ### Commits created while this push was running would otherwise wait for the next backup
        if not self._queued_or_running:
            self._request_push_flush()
    ###### ========================================

    ###### ========================================
    ### Background Notification Section
    def _send_notification_in_background(self, *args, **kwargs) -> None:
        """Send a notification without holding up the backup worker that produced it."""
        task = asyncio.create_task(self._send_notification(*args, **kwargs))
        self._notification_tasks.add(task)
        task.add_done_callback(self._notification_tasks.discard)

    async def _send_notification(self, *args, **kwargs) -> None:
        """Send a notification, limited to MAX_CONCURRENT_NOTIFICATIONS at a time."""
        async with self._get_notification_semaphore():
            try:
                await notification_service.send_notification(*args, **kwargs)
            except Exception as ex:
                logger.warning("Sending notification failed: %s", ex)
    ###### ========================================

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
                    job_id=queued_item.job_id,
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
                self._request_push_flush()

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

        ### Push commits that are still waiting for the batched push
        ## A finishing flush may start a follow-up flush for late commits, so wait until none is left
        while self._push_flush_task is not None and not self._push_flush_task.done():
            await asyncio.gather(self._push_flush_task, return_exceptions=True)
        if git_service.has_pending_pushes():
            try:
                await git_service.push_pending()
            except Exception as ex:
                logger.error("Pushing pending git commits during shutdown failed: %s", ex)

        ### Give notifications that are still being sent a chance to finish
        if self._notification_tasks:
            _, pending = await asyncio.wait(
                set(self._notification_tasks),
                timeout=NOTIFICATION_SHUTDOWN_TIMEOUT_SECONDS,
            )
            if pending:
                logger.warning("Shutting down with %d notification(s) still unsent", len(pending))

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

    def queue_workers_alive(self) -> bool:
        """Return True if the queue workers were started and none of them has died.

        A dead worker is only replaced the next time a backup is queued, so until then it stays visible here.
        """
        if self._backup_queue is None or not self._queue_workers:
            return False
        return all(not worker.done() for worker in self._queue_workers)

    def get_backup_queue_depth(self) -> int:
        """Return number of queued devices waiting for a worker."""
        ### Depth includes only waiting items in queue, not currently running backups
        if self._backup_queue is None:
            return 0
        return self._backup_queue.qsize()

    async def _queue_device_backups(self, devices: list[DeviceBase], *, source: str) -> tuple[dict[str, str], list[str]]:
        """Queue backups for the given devices, assuming queue workers are already initialized.

        Disabled devices and devices that are already queued or running are skipped. Every queued device gets
        a job with status "pending" right away, so it can be tracked before a worker picks it up.

        Returns:
            Job ID per queued device name, and the names of skipped devices
        """
        if self._backup_queue is None:
            raise RuntimeError("Backup queue is not initialized")

        ### Lock protects dedupe checks and updates against concurrent API/scheduler enqueue calls
        skipped: list[str] = []
        reserved: list[DeviceBase] = []
        state_lock = self._get_queue_state_lock()
        async with state_lock:
            for device in devices:
                if not device.enabled or device.device_name in self._queued_or_running:
                    skipped.append(device.device_name)
                    continue
                ### Reserve device name before enqueue so concurrent callers can't queue duplicates
                self._queued_or_running.add(device.device_name)
                reserved.append(device)

        if skipped:
            logger.debug("Skipped queue for %d device(s) from %s: disabled, already queued or running", len(skipped), source)
        if not reserved:
            return {}, skipped

        queued_at = get_utc_now()
        job_ids = {device.device_name: str(uuid.uuid4()) for device in reserved} # Create Job ID
        jobs = [
            BackupJob(
                id=job_ids[device.device_name],
                device_name=device.device_name,
                group=device.group,
                status="pending",
                timestamp=queued_at,
            )
            for device in reserved
        ]
        ### Add job to live events before committing them to the database
        events = [job_to_dict(job) for job in jobs]

        ### Store the jobs in the DB before queueing them, a worker may pick them up right away
        try:
            await asyncio.to_thread(self._create_pending_jobs, jobs)
        except BaseException:
            ### Only reached when cancelled (_create_pending_jobs handles its own errors), dont leave devices reserved
            self._queued_or_running.difference_update(device.device_name for device in reserved)
            raise

        ### Place the jobs in the backup queue for processing
        enqueued_at = time.perf_counter()
        for device in reserved:
            self._backup_queue.put_nowait(
                QueuedBackupItem(device=device, source=source, enqueued_at=enqueued_at, job_id=job_ids[device.device_name])
            )

        logger.debug(
            "Queued %d backup(s) from %s (queue depth: %d)",
            len(jobs),
            source,
            self.get_backup_queue_depth(),
        )

        ### Notify live update clients about the new jobs
        self._publish_job_events(events)

        return job_ids, skipped

    async def queue_device_backup(self, device: DeviceBase, *, source: str) -> str | None:
        """Queue a single device backup.

        Returns:
            The job ID, or None if the device is disabled or already queued/running
        """
        await self._ensure_backup_queue_workers()
        queued, _ = await self._queue_device_backups([device], source=source)
        return queued.get(device.device_name)

    async def queue_device_backups(self, devices: list[DeviceBase], *, source: str) -> tuple[dict[str, str], list[str]]:
        """Queue multiple device backups.

        Returns:
            Job ID per queued device name, and the names of skipped devices
        """
        await self._ensure_backup_queue_workers()
        return await self._queue_device_backups(devices, source=source)

    ###### ========================================
    ### Live Job Tracking Section
    def _publish_job_events(self, jobs: list[dict]) -> None:
        """Tell live update clients about new or changed jobs."""
        event = {"type": "jobs", "jobs": jobs, "queue_depth": self.get_backup_queue_depth()}
        for queue in self._event_queues:
            queue.put_nowait(event)

    @asynccontextmanager
    async def subscribe_job_events(self) -> AsyncIterator[asyncio.Queue[dict]]:
        """Receive all job events published while the context is open."""
        queue: asyncio.Queue[dict] = asyncio.Queue()
        self._event_queues.add(queue)
        try:
            yield queue
        finally:
            self._event_queues.discard(queue)

    ###### ========================================

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

    def _get_previous_backup_status(self, device_name: str) -> str | None:
        """Fetch the last completed backup status for a device (used for anomaly detection)."""
        try:
            if database.SessionLocal is None:
                return None
            db = database.SessionLocal()
            try:
                return backup_job_service.get_previous_completed_status(db, device_name)
            finally:
                db.close()
        except Exception as ex:
            logger.debug("Could not fetch previous backup status for %s: %s", device_name, ex)
            return None

    def _create_pending_jobs(self, jobs: list[BackupJob]) -> None:
        """Store job records with status 'pending' for freshly queued devices in one transaction.

        If this fails the backups still run, the worker then creates the record when the backup starts.
        """
        try:
            if database.SessionLocal is None:
                return

            db = database.SessionLocal()
            try:
                backup_job_service.create_jobs(db, jobs)
            finally:
                db.close()
        except Exception as e:
            logger.warning("Failed to create %d pending job(s): %s", len(jobs), e)

    def _mark_job_in_progress(self, job_id: str, device: DeviceBase) -> None:
        """Set a job record to 'in_progress', creating it if it wasn't stored when the device was queued."""
        try:
            if database.SessionLocal is None:
                return

            db = database.SessionLocal()
            try:
                ### Try to update the job to 'in_progress', ...
                if backup_job_service.update_job(db=db, job_id=job_id, status="in_progress") is None:
                    ### ... if the job didn't exist, create it as 'in_progress'
                    backup_job_service.create_jobs(db, [BackupJob(
                        id=job_id,
                        device_name=device.device_name,
                        group=device.group,
                        status="in_progress",
                        timestamp=get_utc_now(),
                    )])
                logger.debug(f"Job {job_id} for {device.device_name} is in progress")
            finally:
                db.close()
        except Exception as e:
            logger.warning("Failed to mark job %s for %s as in progress: %s", job_id, device.device_name, e)

    async def _update_job_final_status(self, device: DeviceBase, result: BackupRecord) -> None:
        """Store the final status of a job.

        Args:
            device: Device that was backed up
            result: BackupRecord with final backup result
        """
        job_status = self._map_status_to_job_status(result.status)

        def store() -> None:
            """Runs in a thread, SQLAlchemy is synchronous"""
            try:
                if database.SessionLocal is None or result.job_id is None:
                    return

                db = database.SessionLocal()
                try:
                    backup_job_service.update_job(
                        db=db,
                        job_id=result.job_id,
                        status=job_status,
                        error_message=result.error_message,
                        config_size_bytes=result.config_size_bytes,
                        duration_seconds=result.duration_seconds,
                        metadata_output=result.metadata_output,
                    )
                    logger.debug(f"Updated job {result.job_id} with final status: {job_status}")
                finally:
                    db.close()
            except Exception as e:
                logger.warning("Failed to update job %s: %s", result.job_id, e)

        await asyncio.to_thread(store)

        ### Notify live update clients about the job's final status
        self._publish_job_events([job_to_dict(BackupJob(
            id=result.job_id,
            device_name=device.device_name,
            group=device.group,
            status=job_status,
            timestamp=result.timestamp,
            error_message=result.error_message,
            config_size_bytes=result.config_size_bytes,
            duration_seconds=result.duration_seconds,
        ))])

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
            raise ConfigCaptureValidationError(
                f"Captured config appears invalid (CLI error detected): {error_signature}"
            )

        ### Raise error if config is suspiciously small compared to previous successful backup
        previous_size = self._get_latest_completed_config_size(device_name)
        if previous_size is not None and previous_size >= 8192: # Size in bytes
            minimum_expected_size = max(1024, int(previous_size * 0.20)) # equals to at least 20% of previous size or 1KB, whichever is larger
            if config_size < minimum_expected_size and non_empty_lines < 60:
                raise ConfigCaptureTooSmallError(
                    "Captured config is suspiciously small compared to previous successful backup "
                    f"({config_size} bytes vs previous {previous_size} bytes)"
                )

        return config_size
    ###### ========================================

    async def backup_device(
        self,
        device: DeviceBase,
        *,
        job_id: str | None = None,
        queue_wait_seconds: float | None = None,
        queue_source: str | None = None,
    ) -> BackupRecord:
        """
        Perform backup for a single device.

        Sets the job record to 'in_progress' at start, then updates it with the final status
        when complete.

        Args:
            device: Device to backup

        Returns:
            BackupRecord with backup status and job_id for tracking
        """
        ### Fetch previous status for notification sending
        previous_status = await asyncio.to_thread(self._get_previous_backup_status, device.device_name)

        ### Mark the job as in_progress so the UI can show the backup status immediately
        job_id = job_id or str(uuid.uuid4()) # Create a new job ID if not provided
        await asyncio.to_thread(self._mark_job_in_progress, job_id, device)

        ### Notify live update clients about the new job being in progress
        self._publish_job_events([job_to_dict(BackupJob(
            id=job_id,
            device_name=device.device_name,
            group=device.group,
            status="in_progress",
            timestamp=get_utc_now(),
        ))])

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

            ### Resolve device config once to choose protocol
            settings = get_settings()
            device_config = settings.get_device_config(device.group, device.device_name)
            protocol = str(device_config.get("protocol") or "ssh").strip().lower()

            async def _fetch_config() -> tuple[str, str | None]:
                if protocol == "telnet":
                    return await telnet_service.get_config(
                        device,
                        device_config=device_config,
                    )
                if protocol == "ssh":
                    return await ssh_service.get_config(
                        device,
                        device_config=device_config,
                    )
                if protocol in ("http", "https"):
                    return await http_service.get_config(
                        device,
                        device_config=device_config,
                    )
                raise RuntimeError(f"Unsupported protocol: {protocol}")

            ### Get config from device via SSH, Telnet or HTTP(S)
            for attempt in range(2):
                config, metadata_output = await _fetch_config()
                logger.debug(f"Got config for {device.device_name} ({len(config)} bytes)")
                try:
                    ### Validate config for obvious capture issues before saving to git
                    config_size = await asyncio.to_thread(self._validate_config_capture, device.device_name, config)
                    break
                except ConfigCaptureTooSmallError as ex:
                    if attempt == 0:
                        logger.warning(
                            "Config capture for %s appears too small; retrying once: %s",
                            device.device_name,
                            ex,
                        )
                        continue
                    raise

            ### Save config to git (using device's group)
            commit_hash, has_changes, lines_added, lines_removed = await git_service.save_config(
                device.device_name,
                config,
                group=device.group,
            )

            duration_seconds = max(0.0, time.perf_counter() - started_at)

            ### If no changes detected, return NO_CHANGES status
            if not has_changes:
                logger.info(
                    "No configuration changes detected for %s (%.2fs)",
                    device.device_name,
                    duration_seconds,
                )
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
                await self._update_job_final_status(device, result)

                ### No changes can still be a recovery after a failed backup, so let the notification service decide
                self._send_notification_in_background(
                    device.device_name, device.group, result, previous_status, settings.notifications,
                )
                
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
            await self._update_job_final_status(device, result)
            self._send_notification_in_background(
                device.device_name, device.group, result, previous_status, settings.notifications,
                lines_added=lines_added, lines_removed=lines_removed,
            )
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
            await self._update_job_final_status(device, result)
            self._send_notification_in_background(
                device.device_name, device.group, result, previous_status, get_settings().notifications
            )
            return result


### Singleton instance
backup_service = BackupService()
