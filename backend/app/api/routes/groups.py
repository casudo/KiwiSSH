"""Group management endpoints."""

from fastapi import APIRouter, HTTPException, Query
from app.core import get_settings

router = APIRouter()


@router.get("")
async def list_groups(include_config: bool = Query(False)) -> dict:
    """List all configured groups with standardized response format."""
    settings = get_settings()
    groups = list(settings.groups.keys())
    
    if include_config:
        ### Return group configs
        group_list = [{"name": g, "config": settings.groups.get(g)} for g in groups]
    else:
        ### Return just the group names
        group_list = groups
    
    return {
        "count": len(group_list),
        "groups": group_list,
    }


@router.get("/{group_name}")
async def get_group(group_name: str, include_config: bool = Query(False)) -> dict:
    """Get group configuration details."""
    settings = get_settings()
    
    if group_name not in settings.groups:
        raise HTTPException(status_code=404, detail=f"Group '{group_name}' not found")
    
    if include_config:
        return {
            "name": group_name,
            "config": settings.groups.get(group_name),
        }
    else:
        return {"name": group_name}
