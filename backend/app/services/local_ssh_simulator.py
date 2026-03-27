"""Local SSH simulator for testing without real devices."""

from pathlib import Path

from app.core import get_settings
from app.models.device import Device


class LocalSSHSimulator:
    """Simulates SSH connections using local test device files.

    Instead of connecting to real devices via SSH, this reads configs
    from the tests/devices/ folder. Each device has a config.txt file
    that acts as the current running configuration.
    """

    def __init__(self):
        self.settings = get_settings()
        self.test_devices_dir = Path(__file__).parent.parent.parent.parent / "tests" / "devices"

    def _get_device_config_path(self, device_name: str) -> Path:
        """Get path to device's config file."""
        return self.test_devices_dir / device_name / "config.txt"

    async def get_config(self, device: Device) -> str:
        """
        Get configuration from local test device.

        Args:
            device: Device to get config from

        Returns:
            Device configuration as string

        Raises:
            FileNotFoundError: If device config file doesn't exist
        """
        config_path = self._get_device_config_path(device.device_name)

        if not config_path.exists():
            raise FileNotFoundError(
                f"Test device config not found: {config_path}\nCreate {config_path} with device configuration for testing."
            )

        with open(config_path, encoding="utf-8") as f:
            return f.read()


### Singleton instance
local_ssh_simulator = LocalSSHSimulator()
