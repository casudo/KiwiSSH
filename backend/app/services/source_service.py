"""Device source parsing service."""

import csv
from pathlib import Path

from app.core import get_settings
from app.models.device import Device, DeviceStatus


class SourceService:
    """Service for loading devices from various sources."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._devices_cache: dict[str, Device] = {}
        self._loaded = False

    async def load_devices_from_csv(self) -> list[Device]:
        """Load devices from CSV file.

        CSV columns required: group, device_name, ip_address, enabled
        Vendor and ssh_profile are resolved from downtown.yaml configuration.
        Priority: Node-specific override > Group defaults
        """
        project_root = Path(__file__).parent.parent.parent.parent

        ### Use tests/config/sources for local testing, otherwise use config/sources
        if self.settings.local_test_mode:
            csv_path = project_root / "tests" / "config" / "sources" / "devices.csv"
        else:
            sources_dir = self.settings.config_dir / "sources"
            csv_path = sources_dir / "devices.csv"

        if not csv_path.exists():
            return []

        devices = []
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                group = row.get("group").strip() # TODO: Error if group is missing
                device_name = row["device_name"].strip()

                ### Resolve configuration from downtown.yaml
                device_config = self.settings.get_device_config(group, device_name)

                device = Device(
                    group=group,
                    device_name=device_name,
                    ip_address=row["ip_address"].strip(),
                    vendor=device_config["vendor"],
                    ssh_profile=device_config["ssh_profile"],
                    enabled=row.get("enabled", "true").strip().lower() == "true",
                    status=DeviceStatus.UNKNOWN,
                )
                devices.append(device)
                self._devices_cache[device.device_name] = device

        self._loaded = True
        return devices

    async def load_devices_from_db(self):
        """Load devices from database."""
        # TODO: Implement database loading logic
        return []

    async def get_device(self, device_name: str) -> Device | None:
        """Get a single device by name."""
        if not self._loaded:
            await self.load_devices_from_csv()
        return self._devices_cache.get(device_name)

    async def get_devices_by_group(self, group: str) -> list[Device]:
        """Get all devices in a group."""
        if not self._loaded:
            await self.load_devices_from_csv()
        return [d for d in self._devices_cache.values() if d.group == group]

    async def get_all_devices(self) -> list[Device]:
        """Get all devices."""
        if not self._loaded:
            await self.load_devices_from_csv()
        return list(self._devices_cache.values())

    async def get_enabled_devices(self) -> list[Device]:
        """Get all enabled devices."""
        if not self._loaded:
            await self.load_devices_from_csv()
        return [d for d in self._devices_cache.values() if d.enabled]

    async def get_groups(self) -> list[str]:
        """Get list of all groups."""
        if not self._loaded:
            await self.load_devices_from_csv()
        return list(set(d.group for d in self._devices_cache.values()))

    def invalidate_cache(self) -> None:
        """Clear the device cache to force reload."""
        self._devices_cache.clear()
        self._loaded = False


### Singleton instance
source_service = SourceService()
