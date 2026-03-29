"""SSH Profile management endpoints."""

from fastapi import APIRouter

from app.core import get_settings

router = APIRouter()


@router.get("")
async def list_ssh_profiles() -> dict:
    """List all configured SSH profiles from ssh_profiles.yaml."""
    settings = get_settings()
    ### Extract profiles from the 'profiles' key in ssh_profiles.yaml
    all_profiles = settings.ssh_profiles.get("profiles", {})
    profiles = list(all_profiles.keys())
    return {
        "count": len(profiles),
        "profiles": profiles,
    }


@router.get("/{profile_name}")
async def get_ssh_profile(profile_name: str) -> dict:
    """Get specific ASSH profile configuration details."""
    settings = get_settings()
    all_profiles = settings.ssh_profiles.get("profiles", {})
    
    if profile_name not in all_profiles:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"SSH Profile '{profile_name}' not found")
    
    return all_profiles[profile_name]
