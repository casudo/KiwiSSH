"""Vendor management endpoints."""

from fastapi import APIRouter, HTTPException, Query

from app.services.vendor_service import vendor_service

router = APIRouter()


@router.get("")
async def list_vendors(include_config: bool = Query(False, description="Include full vendor configuration")) -> dict:
    """List all available vendors with standardized response format."""
    vendors = vendor_service.list_vendors()
    
    if include_config:
        ### Return full vendor config for each vendor (including commands)
        vendor_list = [vendor_service.get_vendor(v.get("id")) for v in vendors]
    else:
        ### Return only id and name for list view
        vendor_list = [{"id": v.get("id"), "name": v.get("name")} for v in vendors]
    
    return {
        "count": len(vendor_list),
        "vendors": vendor_list,
    }


@router.get("/{vendor_id}")
async def get_vendor(vendor_id: str) -> dict:
    """Get vendor configuration details (excluding commands)."""
    vendor = vendor_service.get_vendor(vendor_id)

    if not vendor:
        raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' not found")

    ### Return full vendor config but exclude "commands" section (use GET /vendors/{vendor_id}/commands for that)
    vendor_copy = dict(vendor)
    vendor_copy.pop("commands", None)
    return vendor_copy


@router.get("/{vendor_id}/commands")
async def get_vendor_commands(vendor_id: str) -> dict:
    """Get backup commands for a vendor."""
    vendor = vendor_service.get_vendor(vendor_id)

    if not vendor:
        raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' not found")

    return vendor_service.get_backup_commands(vendor_id)
