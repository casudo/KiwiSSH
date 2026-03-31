"""Backup-related Pydantic models."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class BackupStatus(str, Enum):
    """Backup operation status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    NO_CHANGES = "no_changes"
    FAILED = "failed"


class BackupRecord(BaseModel):
    """Record of a backup operation."""

    id: str = Field(..., description="Unique backup ID (git commit hash)")
    device_name: str
    timestamp: datetime
    status: BackupStatus
    job_id: Optional[str] = None  # Database job tracking ID
    git_commit: Optional[str] = None
    error_message: Optional[str] = None
    config_size_bytes: Optional[int] = None


class BackupDiff(BaseModel):
    """Difference between two backup versions."""

    device_name: str
    from_commit: str
    to_commit: str
    from_timestamp: Optional[datetime] = None
    to_timestamp: Optional[datetime] = None
    diff_content: str
    lines_added: int = 0
    lines_removed: int = 0


class BackupTriggerRequest(BaseModel):
    """Request to trigger a backup."""

    group: Optional[str] = Field(
        default=None,
        description="Backup all devices in this group.",
    )


class BackupTriggerResponse(BaseModel):
    """Response after triggering backup."""

    message: str
    devices_queued: list[str]
    job_id: Optional[str] = None
