"""Backup operation endpoints."""

import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session

from app.models.backup import BackupTriggerRequest, BackupTriggerResponse
from app.services.backup_service import backup_service
from app.services.source_service import source_service
from app.services.git_service import git_service
from app.db.database import get_db
from sqlalchemy import desc, func
from app.db.models import BackupJob

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/trigger", response_model=BackupTriggerResponse)
async def trigger_backup(
    request: BackupTriggerRequest,
) -> BackupTriggerResponse:
    """Trigger a backup operation for a specific group or all devices."""
    logger.debug(f"Backup trigger endpoint called for group: {request.group or 'all'}")

    ### Get devices to backup
    if request.group:
        devices = await source_service.get_devices_by_group(request.group)
    else: # group: ""
        devices = await source_service.get_all_devices()

    enabled_devices = [d for d in devices if d.enabled]

    if not enabled_devices:
        return BackupTriggerResponse(
            message=f"No enabled devices found for group {request.group}" if request.group else "No enabled devices found",
            devices_queued=[],
            job_id=None,
        )

    context_label = f"group '{request.group}'" if request.group else "all enabled devices"
    queue_source = f"api:group:{request.group}" if request.group else "api:all"
    queued_devices, skipped_devices = await backup_service.queue_device_backups(
        enabled_devices,
        source=queue_source,
    )
    queue_depth = backup_service.get_backup_queue_depth()

    if not queued_devices:
        return BackupTriggerResponse(
            message=(
                f"No new backups queued for {context_label}. "
                f"{len(skipped_devices)} device(s) are already queued or currently running."
            ),
            devices_queued=[],
            job_id=None,
        )

    return BackupTriggerResponse(
        message=(
            f"Queued {len(queued_devices)} backup(s) for {context_label}. "
            f"Skipped {len(skipped_devices)} already queued/running device(s). "
            f"Current queue depth: {queue_depth}."
        ),
        devices_queued=queued_devices,
        job_id=None,
    )


@router.post("/trigger/{device_name}", response_model=BackupTriggerResponse)
async def trigger_device_backup(
    device_name: str,
) -> BackupTriggerResponse:
    """Trigger backup for a specific device."""
    logger.debug(f"Backup trigger endpoint called for: {device_name}")
    device = await source_service.get_device(device_name)
    logger.debug(f"Device found: {device is not None}")

    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_name}' not found")

    queued = await backup_service.queue_device_backup(device, source=f"api:device:{device_name}")
    if not queued:
        return BackupTriggerResponse(
            message=f"Backup for device {device_name} is already queued or currently running.",
            devices_queued=[],
            job_id=None,
        )

    return BackupTriggerResponse(
        message=(
            f"Queued backup for device {device_name}. "
            f"Current queue depth: {backup_service.get_backup_queue_depth()}."
        ),
        devices_queued=[device_name],
        job_id=None,
    )


@router.get("/jobs")
async def get_backup_jobs(
    device_name: str | None = Query(None, description="Filter by partial device name"),
    job_id: str | None = Query(None, description="Filter by partial job ID"),
    status: str | None = Query(None, description="Filter by status (success, failed, no_changes)"),
    limit: int = Query(5000, ge=1, le=50000, description="Maximum number of jobs to return"),
    offset: int = Query(0, ge=0, description="Number of jobs to skip before returning results"),
    db: Session = Depends(get_db),
) -> dict:
    """Get backup job records from the database."""
    try:
        base_query = db.query(BackupJob)
        if device_name:
            base_query = base_query.filter(BackupJob.device_name.ilike(f"%{device_name}%"))
        if job_id:
            base_query = base_query.filter(BackupJob.id.ilike(f"%{job_id}%"))

        status_totals = {
            "pending": 0,
            "in_progress": 0,
            "success": 0,
            "failed": 0,
            "no_changes": 0,
        }
        grouped_counts = base_query.with_entities(BackupJob.status, func.count(BackupJob.id)).group_by(BackupJob.status).all()
        for row_status, row_count in grouped_counts:
            if row_status in status_totals:
                status_totals[row_status] = int(row_count)

        query = base_query
        if status:
            query = query.filter(BackupJob.status == status)

        total_count = query.count()
        avg_duration_value = query.filter(BackupJob.duration_seconds.isnot(None)).with_entities(
            func.avg(BackupJob.duration_seconds)
        ).scalar()
        jobs = query.order_by(desc(BackupJob.timestamp)).offset(offset).limit(limit).all()

        return {
            "count": len(jobs),
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "avg_duration_seconds": float(avg_duration_value) if avg_duration_value is not None else None,
            "status_totals": status_totals,
            "jobs": [
                {
                    "job_id": job.id,
                    "device_name": job.device_name,
                    "group": job.group,
                    "status": job.status,
                    "timestamp": job.timestamp.isoformat() if job.timestamp else None,
                    "error_message": job.error_message,
                    "config_size_bytes": job.config_size_bytes,
                    "duration_seconds": job.duration_seconds,
                    "metadata_output": job.metadata_output,
                }
                for job in jobs
            ],
        }
    except Exception as e:
        logger.error(f"Error fetching backup jobs: {e}")
        return {
            "jobs": [],
            "count": 0,
            "error": str(e),
        }


@router.get("/status/{job_id}")
async def get_backup_job_status(job_id: str) -> dict:
    """Get status of a backup job."""
    return await backup_service.get_backup_status(job_id)


@router.get("/history/{device_name}")
async def get_device_backup_history(
    device_name: str,
    limit: int | None = Query(None, ge=1, description="Maximum number of history entries to return. Omit for all."),
) -> dict:
    """Get backup history for a device."""
    device = await source_service.get_device(device_name)

    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_name}' not found")

    try:
        history = await git_service.get_config_history(device_name, group=device.group, limit=limit)
        return {
            "device_name": device_name,
            "history": history,
            "count": len(history),
        }
    except Exception as e:
        return {
            "device_name": device_name,
            "history": [],
            "error": str(e),
        }


@router.get("/diff/{device_name}")
async def get_config_diff(
    device_name: str,
    from_commit: str,
    to_commit: str,
) -> dict:
    """Get diff between two configuration versions."""
    device = await source_service.get_device(device_name)

    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_name}' not found")

    try:
        diff = await git_service.get_diff(device_name, from_commit, to_commit, group=device.group)
        return {
            "device_name": diff.device_name,
            "from_commit": diff.from_commit,
            "to_commit": diff.to_commit,
            "from_timestamp": diff.from_timestamp.isoformat() if diff.from_timestamp else None,
            "to_timestamp": diff.to_timestamp.isoformat() if diff.to_timestamp else None,
            "diff": diff.diff_content,
            "lines_added": diff.lines_added,
            "lines_removed": diff.lines_removed,
        }
    except Exception as e:
        return {
            "device_name": device_name,
            "from_commit": from_commit,
            "to_commit": to_commit,
            "error": str(e),
            "diff": "",
        }


@router.get("/latest/{device_name}")
async def get_latest_config(device_name: str, commit: str | None = None) -> dict:
    """Get the latest (or specific) backed up configuration for a device."""
    device = await source_service.get_device(device_name)

    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_name}' not found")

    try:
        ### If commit is specified, use that, otherwise get the latest
        if commit:
            config = await git_service.get_config_at_commit(device_name, commit, group=device.group)
            ### Get commit info from history
            history = await git_service.get_config_history(device_name, group=device.group, limit=None)
            commit_info = next((c for c in history if c["hash"] == commit), None)

            return {
                "device_name": device_name,
                "config": config,
                "commit": commit,
                "timestamp": commit_info["timestamp"] if commit_info else None,
                "message": commit_info["message"] if commit_info else None,
                "version_number": commit_info.get("version_number") if commit_info else None,
            }
        else:
            ### Get latest
            history = await git_service.get_config_history(device_name, group=device.group, limit=1)
            if not history:
                return {
                    "device_name": device_name,
                    "config": None,
                    "commit": None,
                    "timestamp": None,
                    "message": "No backup history found",
                }

            latest = history[0]
            config = await git_service.get_config_at_commit(device_name, latest["hash"], group=device.group)

            return {
                "device_name": device_name,
                "config": config,
                "commit": latest["hash"],
                "timestamp": latest["timestamp"],
                "message": latest["message"],
                "version_number": latest.get("version_number"),
            }
    except Exception as e:
        return {
            "device_name": device_name,
            "config": None,
            "error": str(e),
        }


@router.delete("/flush")
async def flush_database(db: Session = Depends(get_db)) -> dict:
    """Delete all backup job records from the database.

    WARNING: This action cannot be undone. All job history will be permanently deleted.
    """
    try:
        ### Get count of jobs to be deleted
        job_count = db.query(BackupJob).count()

        ### Delete all jobs
        db.query(BackupJob).delete()
        db.commit()

        logger.info(f"Flushed database: deleted {job_count} backup jobs")

        return {
            "message": f"Successfully deleted {job_count} backup jobs",
            "deleted_count": job_count,
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to flush database: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to flush database: {str(e)}")
