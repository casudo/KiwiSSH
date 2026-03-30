"""Favorite device endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.favorite_service import favorite_service
from app.services.source_service import source_service

router = APIRouter()

### TODO: Merge favorite endpoints into devices endpoints? /devices/favorites/<device>?

@router.get("")
async def list_favorites(db: Session = Depends(get_db)) -> dict:
    """List all favorite devices."""
    favorites = favorite_service.list_favorites(db)
    return {
        "count": len(favorites),
        "favorites": favorites,
    }


@router.put("/{device_name}")
async def add_favorite(device_name: str, db: Session = Depends(get_db)) -> dict:
    """Mark a device as favorite."""
    device = await source_service.get_device(device_name)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_name}' not found")

    created = favorite_service.add_favorite(db, device_name)
    return {
        "device_name": device_name,
        "added_to_favorites": created,
    }


@router.delete("/{device_name}")
async def remove_favorite(device_name: str, db: Session = Depends(get_db)) -> dict:
    """Unmark a device as favorite."""
    removed = favorite_service.remove_favorite(db, device_name)
    return {
        "device_name": device_name,
        "removed_from_favorites": removed,
    }
