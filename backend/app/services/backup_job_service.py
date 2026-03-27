"""Service for managing backup job records in the database."""

from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db.models import BackupJob


class BackupJobService:
    """Service for persisting and retrieving backup job records."""

    @staticmethod
    def create_job(
        db: Session,
        job_id: str,
        device_name: str,
        group: str,
        status: str,
        error_message: str | None = None,
        config_size_bytes: int | None = None,
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

        Returns:
            Created BackupJob record
        """
        job = BackupJob(
            id=job_id,
            device_name=device_name,
            group=group,
            status=status,
            timestamp=datetime.now(timezone.utc),
            error_message=error_message,
            config_size_bytes=config_size_bytes,
        )
        db.add(job)
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
