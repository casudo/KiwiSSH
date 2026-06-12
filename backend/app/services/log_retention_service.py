"""Service for enforcing backup job log retention policies.

Deletes old backup job records from the database based on configured limits:
- max_age_days: remove records older than N days
- max_rows: remove the oldest records when the total line count exceeds N
"""

import logging
from datetime import timedelta

from sqlalchemy.orm import Session
from sqlalchemy import asc, func

from app.db.models import BackupJob
from app.utils.timezone import get_utc_now

logger = logging.getLogger(__name__)


class LogRetentionService:
    """Enforces retention limits on the backup_jobs table."""

    def run(
        self,
        db: Session,
        max_age_days: int,
        max_rows: int,
    ) -> dict[str, int]:
        """Apply retention policies and return counts of deleted records.

        Policies applied in order:
        1. Age-based: delete records older than *max_age_days* days.
        2. Row-count cap: if the total row count exceeds *max_rows*, delete the oldest rows until the limit is met.

        Args:
            db: SQLAlchemy database session.
            max_age_days: Maximum age of records in days.
            max_rows: Maximum number of records to keep.

        Returns:
            Dictionary with keys `deleted_age` and `deleted_rows` indicating how many records were removed by each policy.
        """
        deleted_age = 0
        deleted_rows = 0

        ### --- Policy 1: age-based deletion ---
        cutoff = get_utc_now() - timedelta(days=max_age_days)
        try:
            result = db.query(BackupJob).filter(BackupJob.timestamp < cutoff).delete(
                synchronize_session=False
            )
            deleted_age = result or 0
            db.commit()
            if deleted_age:
                logger.info(
                    "Log retention: removed %d record(s) older than %d days",
                    deleted_age,
                    max_age_days,
                )
        except Exception as exc:
            db.rollback()
            logger.error("Log retention age policy failed: %s", exc)

        ### --- Policy 2: row-count cap ---
        try:
            total: int = db.query(func.count(BackupJob.id)).scalar() or 0
            excess = total - max_rows
            if excess > 0:
                ### Fetch IDs of the oldest *excess* records
                oldest_ids = (
                    db.query(BackupJob.id)
                    .order_by(asc(BackupJob.timestamp))
                    .limit(excess)
                    .all()
                )
                ### Extract IDs from the query result
                id_list = [row[0] for row in oldest_ids]
                deleted_rows = (
                    db.query(BackupJob)
                    .filter(BackupJob.id.in_(id_list))
                    .delete(synchronize_session=False)
                ) or 0
                db.commit()
                if deleted_rows:
                    logger.info(
                        "Log retention: removed %d record(s) exceeding the %d-row limit",
                        deleted_rows,
                        max_rows,
                    )
        except Exception as exc:
            db.rollback()
            logger.error("Log retention row-cap policy failed: %s", exc)

        ### Return counts
        return {"deleted_age": deleted_age, "deleted_rows": deleted_rows}


log_retention_service = LogRetentionService()
