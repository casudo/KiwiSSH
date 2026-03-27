"""Backup operation endpoints."""

from fastapi import APIRouter, HTTPException

from app.models.backup import BackupTriggerRequest, BackupTriggerResponse
from app.services.backup_service import backup_service
from app.services.source_service import source_service
from app.services.git_service import git_service

router = APIRouter()


@router.post("/trigger", response_model=BackupTriggerResponse)
async def trigger_backup(request: BackupTriggerRequest) -> BackupTriggerResponse:
    """Trigger a backup operation for a specific group."""
    return await backup_service.backup_all(group=request.group)
    ## TODO: Switch to "/trigger/{group_name}" to match trigger_device_backup endpoint and simplify request?


@router.post("/trigger/{device_name}")
async def trigger_device_backup(device_name: str) -> dict:
    """Trigger backup for a specific device."""
    print(f"📢 Backup trigger endpoint called for: {device_name}")
    device = await source_service.get_device(device_name)
    print(f"   Device found: {device is not None}")

    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_name}' not found")

    print(f"   Starting backup for: {device.device_name} (group: {device.group})")
    result = await backup_service.backup_device(device)
    print(f"   Backup result: {result.status.value}")

    return {
        "message": f"Backup triggered for {device_name}",
        "backup_id": result.id,
        "status": result.status.value,
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

