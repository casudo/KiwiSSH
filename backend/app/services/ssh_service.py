"""SSH connection service using asyncssh.

This service handles SSH connections to network devices with support for
legacy ciphers and key exchange algorithms.

TODO: Implement actual SSH connection logic using asyncssh, including
handling of different SSH profiles and vendor-specific quirks.
"""

import asyncio
import logging
from typing import Any

from app.core import get_settings
from app.models.device import DeviceBase

logger = logging.getLogger(__name__)


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
        """Get device configuration via local simulator or real SSH."""
        ### Get device config
        device_config = self.settings.get_device_config(device.group, device.device_name)

        ### Filter for required SSH config values
        timeout_seconds = int(device_config["timeout"])
        retry_count = int(device_config["retry"])
        vendor_id = str(device_config["vendor"]).strip()
        ssh_profile = str(device_config["ssh_profile"]).strip()
        max_attempts = retry_count + 1

        ### Use the local simulator if test mode is enabled
        if self.settings.local_test_mode:
            return await asyncio.wait_for(
                local_ssh_simulator.get_config(device),
                timeout=timeout_seconds,
            )

        ### Try to fetch config from device with commands defined in vendor YAML, apply retries on failure
        last_exception: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            connection: asyncssh.SSHClientConnection | None = None
            try:
                ### Connect via SSH using SSH profile options
                connection = await self.connect(
                    device=device,
                    username=username,
                    password=password,
                    ssh_profile=ssh_profile,
                    timeout=timeout_seconds,
                )

                ### Fun part: Run the configured command phases to capture device config
                config = await self._collect_vendor_config(
                    connection=connection,
                    vendor_id=vendor_id,
                    default_timeout=timeout_seconds,
                    resolved_password=password,
                )
                return config
            except asyncio.TimeoutError as ex:
                ### Log timeout error if SSH connection times out or if waiting for command output exceeds timeout
                last_exception = TimeoutError(
                    f"SSH config fetch timed out after {timeout_seconds}s "
                    f"(attempt {attempt}/{max_attempts})"
                )
                logger.warning(
                    "Config fetch timeout for device '%s' on attempt %d/%d",
                    device.device_name,
                    attempt,
                    max_attempts,
                )
                logger.debug("Timeout details: %s", ex)
            except Exception as ex:
                ### Log any other exceptions that occur during connection or command execution
                ## TODO: Be more specific in exception handling. Log top 3 most common exception types?
                last_exception = ex
                logger.warning(
                    "Config fetch failed for device '%s' on attempt %d/%d: %s",
                    device.device_name,
                    attempt,
                    max_attempts,
                    ex,
                )
            finally:
                ### Ensure connection is properly closed to avoid resource leaks, even on failure
                if connection is not None:
                    connection.close()
                    try:
                        await connection.wait_closed()
                    except Exception:
                        pass

            if attempt < max_attempts:
                await asyncio.sleep(0.25)

        if last_exception is not None:
            raise last_exception
        raise RuntimeError("SSH config fetch failed without a captured exception!!")


### Singleton instance
ssh_service = SSHService()
