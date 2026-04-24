"""Service for managing backup job records in the database."""

from sqlalchemy.orm import Session
from sqlalchemy import desc, update
from app.db.models import BackupJob
from app.utils.timezone import get_utc_now



class BackupJobService:
    """Service for persisting and retrieving backup job records."""

    @staticmethod
    def mark_stuck_jobs_as_failed(db: Session) -> int:
        """Mark all in_progress and pending jobs as failed during startup recovery.
        
        This handles the case where the backend crashed/stopped while backups were running.
        Those jobs will never complete, so they should be marked as failed.
        
        Args:
            db: Database session
            
        Returns:
            Number of jobs marked as failed
        """
        result = db.execute(
            update(BackupJob)
            .where(BackupJob.status.in_(["in_progress", "pending"]))
            .values(
                status="failed",
                error_message="Marked failed during startup recovery - backend shutdown interrupted this job",
                timestamp=get_utc_now(),
            )
        )
        db.commit()
        return result.rowcount or 0

    @staticmethod
    def create_job(
        db: Session,
        job_id: str,
        device_name: str,
        group: str,
        status: str,
        error_message: str | None = None,
        config_size_bytes: int | None = None,
        duration_seconds: float | None = None,
        metadata_output: str | None = None,
    ) -> BackupJob:
        """Create and store a backup job record.

        Args:
            db: Database session
            job_id: Unique job ID (git commit hash or UUID)
            device_name: Name of the device
            group: Device group
            status: Job status (success or failed)
            error_message: Error message if failed
            config_size_bytes: Size of backed up config
            duration_seconds: Time spent in backup operation in seconds
            metadata_output: Optional metadata output captured from comment commands

        Returns:
            Created BackupJob record
        """
        job = BackupJob(
            id=job_id,
            device_name=device_name,
            group=group,
            status=status,
            timestamp=get_utc_now(),
            error_message=error_message,
            config_size_bytes=config_size_bytes,
            duration_seconds=duration_seconds,
            metadata_output=metadata_output,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def update_job(
        db: Session,
        job_id: str,
        status: str,
        error_message: str | None = None,
        config_size_bytes: int | None = None,
        duration_seconds: float | None = None,
        metadata_output: str | None = None,
    ) -> BackupJob | None:
        """Update an existing backup job record by job ID.

        Args:
            db: Database session
            job_id: Existing job ID
            status: New job status
            error_message: Error details for failed jobs
            config_size_bytes: Size of backed up config
            duration_seconds: Time spent in backup operation in seconds
            metadata_output: Optional metadata output captured from comment commands

        Returns:
            Updated BackupJob record or None when not found
        """

        job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
        if job is None:
            return None

        job.status = status
        job.timestamp = get_utc_now()
        job.error_message = error_message
        job.config_size_bytes = config_size_bytes
        job.duration_seconds = duration_seconds
        job.metadata_output = metadata_output
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def get_latest_job(db: Session, device_name: str) -> BackupJob | None:
        """Get the most recent backup job for a device.

        Args:
            db: Database session
            device_name: Name of the device

        Returns:
            Latest BackupJob record or None if no jobs exist
        """
        return db.query(BackupJob).filter(
            BackupJob.device_name == device_name
        ).order_by(
            desc(BackupJob.timestamp)
        ).first()

    ### Helper method for config size validation
    @staticmethod
    def get_latest_completed_job(db: Session, device_name: str) -> BackupJob | None:
        """Get the most recent completed backup job with known config size for a device."""
        return db.query(BackupJob).filter(
            BackupJob.device_name == device_name,
            BackupJob.status.in_(["success", "no_changes"]),
            BackupJob.config_size_bytes.isnot(None),
        ).order_by(
            desc(BackupJob.timestamp)
        ).first()

    @staticmethod
    def get_latest_jobs_for_devices(db: Session, device_names: list[str]) -> dict[str, BackupJob]:
        """Get the most recent backup job for multiple devices in a single query.

        Args:
            db: Database session
            device_names: List of device names

        Returns:
            Dictionary mapping device_name to latest BackupJob record
        """
        if not device_names:
            return {}

        ### Get all jobs for these devices, ordered by timestamp
        jobs = db.query(BackupJob).filter(
            BackupJob.device_name.in_(device_names)
        ).order_by(
            BackupJob.device_name,
            desc(BackupJob.timestamp)
        ).all()

        ### Build dict with latest job per device
        latest_jobs = {}
        for job in jobs:
            if job.device_name not in latest_jobs:
                latest_jobs[job.device_name] = job

        return latest_jobs

    @staticmethod
    def get_device_jobs(db: Session, device_name: str, limit: int = 10) -> list[BackupJob]:
        """Get backup job history for a device.

        Args:
            db: Database session
            device_name: Name of the device
            limit: Maximum number of records to return

        Returns:
            List of BackupJob records
        """
        return db.query(BackupJob).filter(
            BackupJob.device_name == device_name
        ).order_by(
            desc(BackupJob.timestamp)
        ).limit(limit).all()

    @staticmethod
    def get_failed_jobs(db: Session, limit: int = 50) -> list[BackupJob]:
        """Get recent failed backup jobs.

        Args:
            db: Database session
            limit: Maximum number of records to return

        Returns:
            List of failed BackupJob records
        """
        return db.query(BackupJob).filter(
            BackupJob.status == "failed"
        ).order_by(
            desc(BackupJob.timestamp)
        ).limit(limit).all()


### Singleton instance
backup_job_service = BackupJobService()
