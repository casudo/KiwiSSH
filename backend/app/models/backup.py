"""Backup-related Pydantic models."""

from enum import Enum

from pydantic import AwareDatetime, BaseModel, Field, field_validator

from app.utils.timezone import get_utc_now


class BackupStatus(str, Enum):
    """Backup operation status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    NO_CHANGES = "no_changes"
    FAILED = "failed"


class BackupRecord(BaseModel):
    """Record of a backup operation."""

    id: str = Field(..., min_length=1, description="Git commit hash for successful backups, otherwise a random UUID")
    device_name: str = Field(..., min_length=1)
    timestamp: AwareDatetime = Field(default_factory=get_utc_now)
    status: BackupStatus
    job_id: str | None = None # Database job tracking ID
    git_commit: str | None = None # Only set when a new commit was created
    error_message: str | None = None
    config_size_bytes: int | None = Field(default=None, ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)
    metadata_output: str | None = None


class BackupDiff(BaseModel):
    """Difference between two backup versions."""

    device_name: str = Field(..., min_length=1)
    from_commit: str = Field(..., min_length=1)
    to_commit: str = Field(..., min_length=1)
    from_timestamp: AwareDatetime | None = None
    to_timestamp: AwareDatetime | None = None
    diff_content: str
    lines_added: int = Field(default=0, ge=0)
    lines_removed: int = Field(default=0, ge=0)


class BackupTriggerRequest(BaseModel):
    """Request to trigger a backup."""

    group: str | None = Field(
        default=None,
        description="Backup all enabled devices in this group. Leave empty to back up all enabled devices.",
    )

    @field_validator("group", mode="before")
    @classmethod
    def normalize_group(cls, group: object) -> object:
        """Trim the group name, blank means all devices."""
        if isinstance(group, str):
            return group.strip() or None
        return group


class BackupTriggerResponse(BaseModel):
    """Response after triggering backup."""

    message: str
    devices_queued: list[str] = Field(default_factory=list)
    job_id: str | None = None # Not used yet, every queued device gets its own job
