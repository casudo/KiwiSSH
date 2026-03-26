"""Pydantic models for Project Downtown."""

from app.models.device import (
    Device,
    DeviceBase,
    DeviceResponse,
    DeviceStatus,
)
from app.models.backup import (
    BackupDiff,
    BackupRecord,
    BackupStatus,
    BackupTriggerRequest,
    BackupTriggerResponse,
)
