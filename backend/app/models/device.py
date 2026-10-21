"""Device-related Pydantic models."""

import ipaddress
import re
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

### One DNS label: letters, digits, hyphens and (common in internal DNS) underscores, no leading/trailing hyphen
_HOSTNAME_LABEL_RE = re.compile(r"^(?!-)[A-Za-z0-9_-]{1,63}(?<!-)$")


def normalize_device_address(value: object) -> str:
    """Validate a device address and return it normalized.

    Accepts IPv4/IPv6 addresses (returned in canonical form) and hostnames/FQDNs.
    """
    text = str(value).strip()
    ### Allow IPv6 written in URL style, e.g. [2001:db8::1]
    candidate = text[1:-1] if text.startswith("[") and text.endswith("]") else text
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        pass

    hostname = text[:-1] if text.endswith(".") else text # a trailing dot marks a fully qualified name
    labels = hostname.split(".")
    if (
        not hostname
        or len(hostname) > 253
        or not all(_HOSTNAME_LABEL_RE.match(label) for label in labels)
        ### An all-numeric last label means a mistyped IP address (e.g. 10.0.0.256), not a hostname
        or labels[-1].isdigit()
    ):
        raise ValueError(f"'{text}' is neither a valid IP address nor a valid hostname")
    return text


class DeviceStatus(str, Enum):
    """Device backup status."""

    UNKNOWN = "unknown"
    BACKUP_SUCCESS = "backup_success"
    BACKUP_FAILED = "backup_failed"
    BACKUP_IN_PROGRESS = "backup_in_progress"
    BACKUP_NO_CHANGES = "backup_no_changes"


class DeviceBase(BaseModel):
    """Device configuration (static fields from source)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    device_name: str = Field(..., min_length=1, max_length=255)
    ### TODO: Might change 'ip_address' to a more generic 'address' field in the future
    ## NOTE: This will be a BREAKING CHANGE if implemented
    ip_address: str = Field(..., max_length=255) # hostnames/FQDNs are accepted too
    vendor: str = Field(..., min_length=1, max_length=255)
    group: str = Field(..., min_length=1, max_length=255)
    ssh_profile: str = Field(..., min_length=1, max_length=255)
    protocol: Literal["ssh", "telnet", "http", "https"]
    port: int = Field(..., ge=1, le=65535)
    enabled: bool = True

    @field_validator("device_name")
    @classmethod
    def validate_device_name(cls, device_name: str) -> str:
        """Reject names that can't be used as a file name, the config is stored as '<device_name>.conf'."""
        if "/" in device_name or "\\" in device_name or not device_name.isprintable():
            raise ValueError("device_name must not contain slashes or control characters")
        return device_name

    @field_validator("ip_address", mode="before")
    @classmethod
    def validate_ip_address(cls, value: object) -> str:
        """Accept an IP address or a hostname/FQDN."""
        return normalize_device_address(value)


class DeviceFull(DeviceBase):
    """Device config + backup/status information."""

    status: DeviceStatus = DeviceStatus.UNKNOWN
    last_backup: datetime | None = None
    last_backup_success: datetime | None = None
    last_error: str | None = None

    model_config = ConfigDict(from_attributes=True)
