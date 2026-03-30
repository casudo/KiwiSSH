"""SSH Profile management endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.core import get_settings

router = APIRouter()


def _all_profiles(settings: Any) -> dict[str, dict[str, Any]]:
    """Return all SSH profiles from config in a stable map format."""

    profiles = settings.ssh_profiles.get("profiles")
    if not isinstance(profiles, dict):
        return {}
    return profiles


@router.get("")
async def list_ssh_profiles(include_config: bool = Query(False, description="Include full SSH profile configuration")) -> dict:
    """List all configured SSH profiles from ssh_profiles.yaml with standardized response format."""
    settings = get_settings()
    all_profiles = _all_profiles(settings)
    profiles = list(all_profiles.keys())
    
    if include_config:
        ### Return full config for each profile
        profile_list = [{"name": p, "config": dict(all_profiles[p])} for p in profiles]
    else:
        ### Return just the profile names
        profile_list = profiles
    
    return {
        "count": len(profile_list),
        "ssh_profiles": profile_list,
    }


@router.get("/{profile_name}")
async def get_ssh_profile(profile_name: str) -> dict:
    """Get specific SSH profile configuration details (full config)."""
    settings = get_settings()
    all_profiles = _all_profiles(settings)
    
    if profile_name not in all_profiles:
        raise HTTPException(status_code=404, detail=f"SSH Profile '{profile_name}' not found")
    
    return dict(all_profiles[profile_name])
