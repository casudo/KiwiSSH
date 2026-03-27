"""Device management endpoints."""

from fastapi import APIRouter, HTTPException, Query

from app.models.device import DeviceResponse, DeviceStatus
from app.services.source_service import source_service
from app.services.git_service import git_service

router = APIRouter()


async def _enrich_device_with_backup_info(device: DeviceResponse) -> DeviceResponse:
    """Add backup stats to device from git history."""
    try:
        history = await git_service.get_config_history(device.device_name, group=device.group, limit=1000)
        if history:
            device.backup_count = len(history)
            device.last_backup = history[0]["timestamp"]
            device.last_backup_success = history[0]["timestamp"]
            device.status = DeviceStatus.BACKUP_SUCCESS
    except Exception:
        ### If git fails, leave device with original values
        pass
    return device


@router.get("", response_model=list[DeviceResponse])
async def list_devices(
    group: str | None = Query(None, description="Filter by group (?group=<group_name>)"),
    enabled_only: bool = Query(False, description="Only return enabled devices"),
) -> list[DeviceResponse]:
    """List all devices."""
    if group:
        devices = await source_service.get_devices_by_group(group)
    else:
        devices = await source_service.get_all_devices()

    if enabled_only:
        devices = [d for d in devices if d.enabled]

    ### Enrich with backup info
    enriched = []
    for device in devices:
        enriched.append(await _enrich_device_with_backup_info(device))

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
async def get_device(device_name: str) -> DeviceResponse:
    """Get a specific device by name."""
    device = await source_service.get_device(device_name)

    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_name}' not found")

    return await _enrich_device_with_backup_info(device)


@router.get("/{device_name}/status")
async def get_device_status(device_name: str) -> dict:
    """Get device status including last backup info."""
    device = await source_service.get_device(device_name)

    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_name}' not found")

    device = await _enrich_device_with_backup_info(device)

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
