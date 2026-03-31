"""SSH connection service using asyncssh.

This service handles SSH connections to network devices with support for
legacy ciphers and key exchange algorithms.

TODO: Implement actual SSH connection logic using asyncssh, including
handling of different SSH profiles and vendor-specific quirks.
"""

from typing import Any

from app.core import get_settings
from app.models.device import DeviceBase


class SSHService:
    """Service for SSH connections to network devices."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def _resolve_timeout_retry(self, device: DeviceBase) -> tuple[int, int]:
        """Resolve timeout/retry with priority: app < group < node."""
        device_config = self.settings.get_device_config(device.group, device.device_name)

        timeout = int(device_config.get("timeout"))
        retry = int(device_config.get("retry"))
        return timeout, retry

    def _get_ssh_options(self, profile_name: str) -> dict[str, Any]:
        """Get SSH options from profile."""
        profile = self.settings.get_ssh_profile(profile_name)

        return {
            "kex_algs": profile.get("kex_algorithms"),
            "encryption_algs": profile.get("ciphers"),
            "server_host_key_algs": profile.get("host_key_algorithms"),
            "known_hosts": profile.get("known_hosts_policy", "ignore").lower(),
        }

    async def connect(
        self,
        device: DeviceBase,
        username: str,
        password: str | None = None,
        key_filename: str | None = None,
    ) -> Any:
        """
        Establish SSH connection to device.

        Args:
            device: Device to connect to
            username: SSH username
            password: SSH password (optional if using key auth)
            key_filename: Path to SSH private key (optional)

        Returns:
            SSH connection object

        Raises:
            NotImplementedError: SSH connection not yet implemented
        """
        raise NotImplementedError("SSH connection not yet implemented")

    async def execute_command(
        self,
        connection: Any,
        command: str,
        timeout: int = 30,
    ) -> str:
        """
        Execute command on device and return output.

        Args:
            connection: Active SSH connection
            command: Command to execute
            timeout: Command timeout in seconds

        Returns:
            Command output string

        Raises:
            NotImplementedError: Command execution not yet implemented
        """
        raise NotImplementedError("Command execution not yet implemented")

    async def get_config(
        self,
        device: DeviceBase,
        username: str,
        password: str,
    ) -> str:
        """
        Get configuration from device using vendor-specific commands.

        For testing/development, uses LocalSSHSimulator to read from local files.

        Args:
            device: Device to get config from
            username: SSH username
            password: SSH password

        Returns:
            Device configuration string

        Raises:
            FileNotFoundError: If test device not found
        """
        ### TODO: FIX: Use local simulator for testing
        from app.services.local_ssh_simulator import local_ssh_simulator

        return await local_ssh_simulator.get_config(device)

    async def test_connection(self, device: DeviceBase, username: str, password: str) -> bool:
        """
        Test if device is reachable via SSH.

        Args:
            device: Device to test
            username: SSH username
            password: SSH password

        Returns:
            True if connection successful, False otherwise
        """
        ### TODO: For base implementation, always returns False (not implemented)
        return False


### Singleton instance
ssh_service = SSHService()
