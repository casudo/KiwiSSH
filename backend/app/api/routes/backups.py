"""Backup operation endpoints."""

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session

from app.models.backup import BackupTriggerRequest, BackupTriggerResponse, BackupStatus
from app.services.backup_service import backup_service
from app.services.source_service import source_service
from app.services.backup_job_service import backup_job_service
from app.services.git_service import git_service
from app.db.database import get_db

router = APIRouter()


@router.post("/trigger", response_model=BackupTriggerResponse)
async def trigger_backup(request: BackupTriggerRequest, db: Session = Depends(get_db)) -> BackupTriggerResponse:
    """Trigger a backup operation for a specific group or all devices."""
    print(f"📢 Backup trigger endpoint called for group: {request.group or 'all'}")

    ### Get devices to backup
    if request.group:
        devices = await source_service.get_devices_by_group(request.group)
    else: # group: ""
        devices = await source_service.get_all_devices()

    enabled_devices = [d for d in devices if d.enabled]
    print(f"   Found {len(enabled_devices)} enabled devices")

    ### Perform backups
    results = await backup_service.backup_devices(enabled_devices)

    ### Log backup jobs to database
    for result in results:
        device = next((d for d in enabled_devices if d.device_name == result.device_name), None) 
        if not device:
            continue

        ### Map backup result status to job status
        if result.status == BackupStatus.NO_CHANGES:
            job_status = "no_changes"
        elif result.status == BackupStatus.SUCCESS:
            job_status = "success"
        else:
            job_status = "failed"

        try:
            backup_job_service.create_job(
                db=db,
                job_id=result.id,
                device_name=result.device_name,
                group=device.group,
                status=job_status,
                error_message=result.error_message,
                config_size_bytes=result.config_size_bytes,
            )
            print(f"   ✓ Logged backup job for {result.device_name}: status={job_status}")
        except Exception as e:
            print(f"   ⚠️ Failed to log backup job for {result.device_name}: {e}")

    successful = [r for r in results if r.status == BackupStatus.SUCCESS]
    device_names = [d.device_name for d in enabled_devices]

    return BackupTriggerResponse(
        message=f"Backup completed for {len(successful)}/{len(device_names)} devices",
        devices_queued=device_names,
        job_id=results[0].id if results else None,
    )


@router.post("/trigger/{device_name}")
async def trigger_device_backup(device_name: str, db: Session = Depends(get_db)) -> dict:
    """Trigger backup for a specific device."""
    print(f"📢 Backup trigger endpoint called for: {device_name}")
    device = await source_service.get_device(device_name)
    print(f"   Device found: {device is not None}")

    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_name}' not found")

    print(f"   Starting backup for: {device.device_name} (group: {device.group})")
    result = await backup_service.backup_device(device)
    print(f"   Backup result: {result.status.value}")

    ### Log backup job to database
    ## Map backup result status to device status and job status
    if result.status == BackupStatus.NO_CHANGES:
        job_status = "no_changes"
    elif result.status == BackupStatus.SUCCESS:
        job_status = "success"
    else:
        job_status = "failed"

    try:
        backup_job_service.create_job(
            db=db,
            job_id=result.id, # Hash or UUID from backup result
            device_name=device_name,
            group=device.group,
            status=job_status,
            error_message=result.error_message,
            config_size_bytes=result.config_size_bytes,
        )
        print(f"   ✓ Backup job logged to database: status={job_status}")
    except Exception as e:
        print(f"   ⚠️ Failed to log backup job: {e}")

    return {
        "message": f"Backup triggered for {device_name}",
        "backup_id": result.id,
        "status": job_status,
    }


@router.get("/jobs")
async def get_backup_jobs(
    device_name: str | None = Query(None, description="Filter by device name"),
    status: str | None = Query(None, description="Filter by status (success, failed)"),
    limit: int = Query(50, description="Maximum number of jobs to return"),
    db: Session = Depends(get_db),
) -> dict:
    """Get backup job records from the database."""
    from sqlalchemy import desc
    from app.db.models import BackupJob

    try:
        if device_name:
            ### Get jobs for a specific device
            jobs = backup_job_service.get_device_jobs(db, device_name, limit)
        else:
            ### Get recent jobs, optionally filtered by status
            query = db.query(BackupJob).order_by(desc(BackupJob.timestamp))
            if status:
                query = query.filter(BackupJob.status == status)
            jobs = query.limit(limit).all()

        return {
            "jobs": [
                {
                    "job_id": job.id,
                    "device_name": job.device_name,
                    "group": job.group,
                    "status": job.status,
                    "timestamp": job.timestamp.isoformat() if job.timestamp else None,
                    "error_message": job.error_message,
                    "config_size_bytes": job.config_size_bytes,
                }
                for job in jobs
            ],
            "count": len(jobs),
        }
    except Exception as e:
        print(f"Error fetching backup jobs: {e}")
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
    limit: int = 10,
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
            history = await git_service.get_config_history(device_name, group=device.group, limit=100)
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

