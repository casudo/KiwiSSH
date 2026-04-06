"""Device management endpoints."""

import logging
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session

from app.models.device import DeviceBase, DeviceFull, DeviceStatus
from app.services.source_service import source_service
from app.services.git_service import git_service
from app.services.backup_job_service import backup_job_service
from app.core.config import get_settings
from app.db.database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


async def _enrich_device_with_backup_info(device_base: DeviceBase, db: Session = None, latest_jobs_cache: dict = None) -> DeviceFull:
    """Add backup info to device from database."""
    device = DeviceFull(**device_base.model_dump())
    try:
        ### Check database for latest backup job status
        if db:
            ### Use cached latest jobs if available, otherwise query individually
            latest_job = None
            if latest_jobs_cache is not None:
                latest_job = latest_jobs_cache.get(device.device_name)
            else:
                latest_job = backup_job_service.get_latest_job(db, device.device_name)

            if latest_job:
                logger.debug(f"Found latest job for {device.device_name}: status={latest_job.status}, timestamp={latest_job.timestamp}")
                device.last_backup = latest_job.timestamp
                if latest_job.status in {"pending", "in_progress"}:
                    device.status = DeviceStatus.BACKUP_IN_PROGRESS
                elif latest_job.status == "success":
                    device.status = DeviceStatus.BACKUP_SUCCESS
                    device.last_backup_success = latest_job.timestamp
                elif latest_job.status == "no_changes":
                    ### No changes is still a successful backup (device connected, backup ran)
                    device.status = DeviceStatus.BACKUP_NO_CHANGES
                    device.last_backup_success = latest_job.timestamp
                elif latest_job.status == "failed":
                    device.status = DeviceStatus.BACKUP_FAILED
                    device.last_error = latest_job.error_message
            else:
                logger.debug(f"No backup job found for {device.device_name}")

    except Exception as e:
        logger.warning(f"Failed to get backup info for {device.device_name}: {e}")
        pass
    return device


@router.get("", response_model=dict)
async def list_devices(
    group: str | None = Query(None, description="Filter by group (?group=<group_name>)"),
    enabled_only: bool = Query(False, description="Only return enabled devices"),
    include_config: bool = Query(False, description="Include full device configuration"),
    db: Session = Depends(get_db),
) -> dict: # TOD: group and enabled_only filters needed?
    """List all devices with standardized response format."""
    if group:
        devices = await source_service.get_devices_by_group(group)
    else:
        devices = await source_service.get_all_devices()

    if enabled_only:
        devices = [d for d in devices if d.enabled]

    enriched_devices: list[DeviceFull] = []
    for device in devices:
        enriched_devices.append(device)

    ### Batch load latest backup jobs for all devices (much faster than per-device queries)
    device_names = [d.device_name for d in enriched_devices]
    latest_jobs = backup_job_service.get_latest_jobs_for_devices(db, device_names)

    ### Enrich with backup info using cached jobs
    enriched = []
    for device in enriched_devices:
        enriched_device = await _enrich_device_with_backup_info(device, db, latest_jobs)
        enriched.append(enriched_device)

    ### Return standardized response format
    if include_config:
        ### Return full device config (using model_dump)
        response_devices = [d.model_dump() for d in enriched]
    else:
        ### Return only device names for minimal list view
        response_devices = [d.device_name for d in enriched]
    
    return {
        "count": len(response_devices),
        "devices": response_devices,
    }


@router.get("/{device_name}", response_model=dict)
async def get_device(device_name: str, db: Session = Depends(get_db)) -> dict:
    """Get a specific device's complete information including backup status."""
    device_base = await source_service.get_device(device_name)

    if device_base is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_name}' not found")

    ### Enrich with backup information
    device = await _enrich_device_with_backup_info(device_base, db)

    ### Get backup count from git history
    backup_count = 0
    try:
        history = await git_service.get_config_history(device_name, group=device.group, limit=None)
        if history:
            backup_count = len(history)
    except Exception:
        pass

    ### Get device schedule
    settings = get_settings()
    device_config = settings.get_device_config(device.group, device_name)
    schedule = device_config.get("schedule")
    schedule_str = f"{schedule.cron} ({schedule.timezone})" if schedule and hasattr(schedule, 'cron') and schedule.cron else None

    ### Return full device config with backup information
    result = device.model_dump()
    result["status"] = device.status.value
    result["backup_count"] = backup_count
    result["schedule"] = schedule_str
    return result


@router.post("/reload")
async def reload_devices() -> dict:
    """Reload devices from source file."""
    source_service.invalidate_cache()
    devices = await source_service.get_all_devices()

    return {
        "message": "Devices reloaded successfully",
        "count": len(devices),
    }
