"""Device management endpoints."""

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session

from app.models.device import DeviceResponse, DeviceListResponse, DeviceStatus
from app.services.source_service import source_service
from app.services.git_service import git_service
from app.services.backup_job_service import backup_job_service
from app.db.database import get_db

router = APIRouter()


async def _enrich_device_with_backup_info(device: DeviceResponse, db: Session = None, latest_jobs_cache: dict = None) -> DeviceResponse:
    """Add backup stats to device from database."""
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
                print(f"[Device Enrichment] Found latest job for {device.device_name}: status={latest_job.status}, timestamp={latest_job.timestamp}") # TODO: Make debug log entry?
                device.last_backup = latest_job.timestamp
                if latest_job.status == "success":
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
                print(f"[Device Enrichment] No backup job found for {device.device_name}")

    except Exception as e:
        print(f"Warning: Failed to get backup info for {device.device_name}: {e}")
        pass
    return device


@router.get("", response_model=list[DeviceListResponse])
async def list_devices(
    group: str | None = Query(None, description="Filter by group (?group=<group_name>)"),
    enabled_only: bool = Query(False, description="Only return enabled devices"),
    db: Session = Depends(get_db),
) -> list[DeviceListResponse]:
    """List all devices."""
    if group:
        devices = await source_service.get_devices_by_group(group)
    else:
        devices = await source_service.get_all_devices()

    if enabled_only:
        devices = [d for d in devices if d.enabled]

    ### Batch load latest backup jobs for all devices (much faster than per-device queries)
    device_names = [d.device_name for d in devices]
    latest_jobs = backup_job_service.get_latest_jobs_for_devices(db, device_names)

    ### Enrich with backup info using cached jobs
    enriched = []
    for device in devices:
        enriched_device = await _enrich_device_with_backup_info(device, db, latest_jobs)
        ### Convert to lightweight response model (excludes backup_count)
        enriched.append(DeviceListResponse.model_validate(enriched_device))

    return enriched


@router.get("/groups")
async def list_groups() -> dict:
    """List all device groups."""
    groups = await source_service.get_groups()
    return {
        "groups": groups,
        "count": len(groups),
    }


@router.get("/{device_name}", response_model=DeviceResponse)
async def get_device(device_name: str, db: Session = Depends(get_db)) -> DeviceResponse:
    """Get a specific device by name."""
    device = await source_service.get_device(device_name)

    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_name}' not found")

    return await _enrich_device_with_backup_info(device, db)


@router.get("/{device_name}/status")
async def get_device_status(device_name: str, db: Session = Depends(get_db)) -> dict:
    """Get device status including last backup info."""
    device = await source_service.get_device(device_name)

    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_name}' not found")

    device = await _enrich_device_with_backup_info(device, db)

    return {
        "device_name": device.device_name,
        "status": device.status.value,
        "last_backup": device.last_backup,
        "last_backup_success": device.last_backup_success,
        "backup_count": device.backup_count,
        "enabled": device.enabled,
    }


@router.post("/reload")
async def reload_devices() -> dict:
    """Reload devices from source file."""
    source_service.invalidate_cache()
    devices = await source_service.get_all_devices()

    return {
        "message": "Devices reloaded successfully",
        "count": len(devices),
    }
