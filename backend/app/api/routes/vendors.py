"""Vendor management endpoints."""

from fastapi import APIRouter, HTTPException

from app.services.vendor_service import vendor_service

router = APIRouter()


@router.get("")
async def list_vendors() -> dict:
    """List all available vendors."""
    vendors = vendor_service.list_vendors()
    return {
        "count": len(vendors),
        "vendors": vendors,
    }


@router.get("/{vendor_id}")
async def get_vendor(vendor_id: str) -> dict:
    """Get vendor configuration details."""
    vendor = vendor_service.get_vendor(vendor_id)

    if not vendor:
        raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' not found")

    return vendor


@router.get("/{vendor_id}/commands")
async def get_vendor_commands(vendor_id: str) -> dict:
    """Get backup commands for a vendor."""
    vendor = vendor_service.get_vendor(vendor_id)

    if not vendor:
        raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' not found")

    return vendor_service.get_backup_commands(vendor_id)
