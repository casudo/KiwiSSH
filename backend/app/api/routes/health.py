"""Health check endpoints."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.core import get_settings
from app.utils.timezone import get_utc_now



class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    timestamp: datetime
    version: str
    config_loaded: bool


router = APIRouter()


@router.get("", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check application health."""
    settings = get_settings()

    return HealthResponse(
        status="healthy",
        timestamp=get_utc_now(),
        version=__version__,
        config_loaded=bool(settings.app and settings.groups and settings.git),
    )


@router.get("/ready")
async def readiness_check() -> dict:
    """Check if application is ready to serve requests."""
    settings = get_settings()

    checks = {
        "config_dir_exists": settings.config_dir.exists(),
        "main_config_exists": (settings.config_dir / "kiwissh.yaml").exists(),
        "ssh_profiles_loaded": bool(settings.ssh_profiles),
        "vendors_loaded": bool(settings.vendors),
    }

    all_ready = all(checks.values())

    return {
        "ready": all_ready,
        "checks": checks,
    }
