"""Group management endpoints."""

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException, Query
from app.core import get_settings

router = APIRouter()

### Secret fields stay in the response so clients can see whether one is set, but their values are masked
## Unset secrets remain None so "not configured" can still be told apart from "configured"
SECRET_FIELDS = {"password", "enable_password"}
SECRET_MASK = "********"


def _mask_url_credentials(url: str | None) -> str | None:
    """Mask credentials embedded in an HTTP(S) URL, e.g. https://user:token@host/repo.git."""
    if not url:
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return url

    ### Any userinfo in an HTTP(S) URL is a secret
    ## SSH URLs carry only a login name like 'git', so they are left untouched
    if parts.scheme.lower() not in ("http", "https") or "@" not in parts.netloc:
        return url
    host = parts.netloc.rsplit("@", 1)[1]
    return urlunsplit(parts._replace(netloc=f"{SECRET_MASK}@{host}"))


def _mask_secrets(value: Any) -> Any:
    """Recursively mask secret values (passwords, credentials in URLs) in a dumped config."""
    if isinstance(value, dict):
        masked: dict[str, Any] = {}
        for key, item in value.items():
            if key in SECRET_FIELDS and item is not None:
                masked[key] = SECRET_MASK
            elif key == "url" and isinstance(item, str):
                masked[key] = _mask_url_credentials(item)
            else:
                masked[key] = _mask_secrets(item)
        return masked
    if isinstance(value, list):
        return [_mask_secrets(item) for item in value]
    return value


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
                "config": _mask_secrets(settings.groups[group_name].model_dump()),
                "git_remote_url": _mask_url_credentials(_resolve_group_remote_url(group_name, settings=settings)),
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
            "config": _mask_secrets(settings.groups[group_name].model_dump()),
            "git_remote_url": _mask_url_credentials(_resolve_group_remote_url(group_name, settings=settings)),
        }
    else:
        return {"name": group_name}
