"""Health check endpoints."""

import asyncio
import os
from datetime import datetime

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app import __version__
from app.core import get_settings
from app.db import database
from app.services.git_service import git_service
from app.services.scheduler_service import scheduler_service
from app.utils.timezone import get_utc_now



class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    timestamp: datetime
    version: str
    config_loaded: bool


class ReadinessResponse(BaseModel):
    """Readiness check response."""

    ready: bool
    checks: dict[str, bool]


router = APIRouter()

### =========================================================================================================
### Helper Functions
### =========================================================================================================

def _database_reachable() -> bool:
    """Run a trivial query to check that the application database answers."""
    if database.engine is None:
        return False
    try:
        with database.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _backup_dir_writable() -> bool:
    """Check that the backup directory (git.local_path) exists and new repositories can be created in it.

    os.access reports a read-only mount as not writable.
    """
    backup_dir = git_service.backups_base_dir
    return backup_dir.is_dir() and os.access(backup_dir, os.W_OK | os.X_OK)

### =========================================================================================================
### API Endpoints
### =========================================================================================================

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


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse, "description": "At least one check failed"}},
)
async def readiness_check(response: Response) -> ReadinessResponse:
    """Check if application is ready to serve requests and run backups.

    Answers with HTTP 503 if any check fails, so container healthchecks and monitoring tools can rely on the status code.
    """
    settings = get_settings()

    ### Run blocking checks in threads to not stall the event loop
    database_connected, backup_dir_writable = await asyncio.gather(
        asyncio.to_thread(_database_reachable),
        asyncio.to_thread(_backup_dir_writable),
    )

    checks = {
        "config_dir_exists": settings.config_dir.exists(),
        "main_config_exists": (settings.config_dir / "kiwissh.yaml").exists(),
        "ssh_profiles_loaded": bool(settings.ssh_profiles),
        "vendors_loaded": bool(settings.vendors),
        "database_connected": database_connected,
        "backup_dir_writable": backup_dir_writable,
        "scheduler_running": scheduler_service.is_running(),
    }

    all_ready = all(checks.values())
    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(ready=all_ready, checks=checks)
