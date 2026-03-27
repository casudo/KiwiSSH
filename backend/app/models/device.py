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
    """Base device model with common fields."""

    device_name: str = Field(..., min_length=1, max_length=255)
    ip_address: IPvAnyAddress
    vendor: str = Field(...)
    group: str = Field(...)
    ssh_profile: str = Field(default="modern")
    enabled: bool = True


class Device(DeviceBase):
    """Full device model with runtime state."""

    status: DeviceStatus = DeviceStatus.UNKNOWN
    last_backup: Optional[datetime] = None
    last_backup_success: Optional[datetime] = None
    backup_count: int = 0
    last_error: Optional[str] = None


class DeviceResponse(Device):
    """API response model for device."""

    model_config = ConfigDict(from_attributes=True)
