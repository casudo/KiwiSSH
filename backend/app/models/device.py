"""Device-related Pydantic models."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress


class DeviceStatus(str, Enum):
    """Device backup status."""

    UNKNOWN = "unknown"
    BACKUP_SUCCESS = "backup_success"
    BACKUP_FAILED = "backup_failed"
    BACKUP_IN_PROGRESS = "backup_in_progress"
    BACKUP_NO_CHANGES = "backup_no_changes"


class DeviceBase(BaseModel):
    """Device configuration (static fields from source)."""

    device_name: str = Field(..., min_length=1, max_length=255)
    ip_address: IPvAnyAddress
    vendor: str = Field(..., min_length=1, max_length=255)
    group: str = Field(..., min_length=1, max_length=255)
    ssh_profile: str = Field(..., min_length=1, max_length=255)
    enabled: bool = True


class DeviceFull(DeviceBase):
    """Device config + backup/status information."""

    status: DeviceStatus = DeviceStatus.UNKNOWN
    last_backup: Optional[datetime] = None
    last_backup_success: Optional[datetime] = None
    last_error: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
