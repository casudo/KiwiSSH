"""Group management endpoints."""

from fastapi import APIRouter, HTTPException, Query
from app.core import get_settings

router = APIRouter()


def _resolve_group_remote_url(group_name: str, settings=None) -> str | None:
    """Resolve effective remote URL for a group using global fallback and overrides."""
    if settings is None:
        settings = get_settings()

    remote_url = settings.git.remote.url if settings.git.remote is not None else None

    ### Check for group override
    group_config = settings.groups.get(group_name)
    if group_config is not None and group_config.git is not None and group_config.git.remote is not None:
        group_remote_url = group_config.git.remote.url
        if group_remote_url is not None:
            remote_url = group_remote_url

    if remote_url is None:
        return None

    try:
        return remote_url.format(group=group_name)
    except (KeyError, ValueError):
        return remote_url


@router.get("")
async def list_groups(include_config: bool = Query(False)) -> dict:
    """List all configured groups with standardized response format."""
    settings = get_settings()
    groups = list(settings.groups.keys())
    
    if include_config:
        ### Return group configs
        group_list = [
            {
                "name": group_name,
                "config": settings.groups[group_name].model_dump(),
                "git_remote_url": _resolve_group_remote_url(group_name, settings=settings),
            }
            for group_name in groups
        ]
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
            "config": settings.groups[group_name].model_dump(),
            "git_remote_url": _resolve_group_remote_url(group_name, settings=settings),
        }
    else:
        return {"name": group_name}
