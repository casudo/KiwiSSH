"""Health check endpoints."""

import asyncio
import os
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app import __version__
from app.core import get_settings
from app.db import database
from app.services.backup_service import backup_service
from app.services.git_service import git_service
from app.services.scheduler_service import scheduler_service
from app.utils.timezone import get_utc_now



class HealthResponse(BaseModel):
    """Health check response."""

    status: Literal["healthy", "unhealthy"]
    timestamp: datetime
    version: str
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

@router.get(
    "",
    response_model=HealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse, "description": "At least one check failed"}},
)
async def health_check(response: Response) -> HealthResponse:
    """Check if the application is healthy and able to run backups.

    Answers with HTTP 503 if any check fails, so container healthchecks and monitoring tools can rely on the status code.
    The body is the same either way, so the version and the failed checks are always available.
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
        "queue_workers_alive": backup_service.queue_workers_alive(),
    }

    healthy = all(checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="healthy" if healthy else "unhealthy",
        timestamp=get_utc_now(),
        version=__version__,
        checks=checks,
    )
