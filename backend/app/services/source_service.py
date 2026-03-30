"""Device source parsing service."""

import csv
from pathlib import Path

from app.core import get_settings
from app.models.device import DeviceBase


class SourceService:
    """Service for loading devices from various sources."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._devices_cache: dict[str, DeviceBase] = {}
        self._loaded = False

    def _get_csv_source_path(self) -> Path:
        """Resolve CSV source path from sources.file string."""

        default_config_path = "/config/sources/devices.csv"

        configured_path = self.settings.sources.file if self.settings.sources else None
        if not configured_path:
            configured_path = default_config_path

        if configured_path.strip() == default_config_path:
            return (self.settings.config_dir / "sources" / "devices.csv").resolve()

        candidate = Path(configured_path)
        if not candidate.is_absolute():
            candidate = self.settings.config_dir / candidate
        return candidate.resolve()

    def _cache_device_from_row(self, row: dict, row_num: int | str) -> None:
        """Build and cache a device from a normalized source row."""

        group = str(row.get("group", "")).strip()
        device_name = str(row.get("device_name", "")).strip()

        if not group:
            raise ValueError(f"Row {row_num}: 'group' column is required")
        if group not in self.settings.groups:
            raise ValueError(
                f"Row {row_num} (device '{device_name}'): Group '{group}' not found in downtown.yaml. "
                f"Available groups: {', '.join(self.settings.groups.keys())}"
            )

        device_config = self.settings.get_device_config(group, device_name)

        enabled_raw = row.get("enabled", True)
        if isinstance(enabled_raw, bool):
            enabled = enabled_raw
        else:
            enabled = str(enabled_raw).strip().lower() == "true"

        device = DeviceBase(
            group=group,
            device_name=device_name,
            ip_address=str(row.get("ip_address", "")).strip(),
            vendor=device_config["vendor"],
            ssh_profile=device_config["ssh_profile"],
            enabled=enabled,
        )
        self._devices_cache[device.device_name] = device
    async def load_devices_from_csv(self) -> list[DeviceBase]:
        """Load devices from CSV file.

        CSV columns required: group, device_name, ip_address, enabled
        Vendor and ssh_profile are resolved from downtown.yaml configuration.
        Priority: Node-specific override > Group defaults
        """
        csv_path = self._get_csv_source_path()

        if not csv_path.exists():
            return []

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_num, row in enumerate(reader, start=2):  # Start at 2 to account for header
                self._cache_device_from_row(row, row_num)

        self._loaded = True
        return list(self._devices_cache.values())

    async def load_devices_from_db(self):
        """Load devices from database."""
        # TODO: Implement database loading logic
        return []

    async def load_devices(self) -> list[DeviceBase]:
        """Load devices from configured source (PostgreSQL preferred, CSV fallback)."""

        return await self.load_devices_from_csv()

    async def get_device(self, device_name: str) -> DeviceBase | None:
        """Get a single device by name."""
        if not self._loaded:
            await self.load_devices()
        return self._devices_cache.get(device_name)

    async def get_devices_by_group(self, group: str) -> list[DeviceBase]:
        """Get all devices in a group."""
        if not self._loaded:
            await self.load_devices()
        return [d for d in self._devices_cache.values() if d.group == group]

    async def get_all_devices(self) -> list[DeviceBase]:
        """Get all devices."""
        if not self._loaded:
            await self.load_devices()
        return list(self._devices_cache.values())

    async def get_enabled_devices(self) -> list[DeviceBase]:
        """Get all enabled devices."""
        if not self._loaded:
            await self.load_devices()
        return [d for d in self._devices_cache.values() if d.enabled]

    async def get_groups(self) -> list[str]:
        """Get list of all groups."""
        if not self._loaded:
            await self.load_devices()
        return list(set(d.group for d in self._devices_cache.values()))

    def invalidate_cache(self) -> None:
        """Clear the device cache to force reload."""
        self._devices_cache.clear()
        self._loaded = False


### Singleton instance
source_service = SourceService()
