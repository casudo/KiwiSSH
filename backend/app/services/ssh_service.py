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
        """Get SSH options from profile and map known_hosts policy."""
        profile = self.settings.get_ssh_profile(profile_name)

        policy = str(profile.get("known_hosts_policy", "ignore")).lower().strip()
        if policy == "strict":
            known_hosts: str | None = str(Path.home() / ".ssh" / "known_hosts")
        else:
            if policy == "auto_add":
                logger.warning(
                    "known_hosts_policy 'auto_add' is not implemented; falling back to 'ignore'"
                )
                ### TODO: Implement auto_add
            known_hosts = None

        ### Map configured SSH profile options to asyncssh.connect kwargs
        return {
            "kex_algs": profile.get("kex_algorithms"),
            "encryption_algs": profile.get("ciphers"),
            "server_host_key_algs": profile.get("host_key_algorithms"),
            "known_hosts": known_hosts,
        }

    async def _read_until_patterns(
        self,
        stream: asyncssh.SSHReader,
        patterns: list[re.Pattern[str]],
        timeout: int,
    ) -> str:
        """Read stream until one of the patterns appears or timeout is reached."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(1, int(timeout))
        buffer = ""

        ### Read in a loop until we see a prompt pattern or hit the timeout
        while True:
            ### Check if any of the patterns match the current buffer content
            if patterns:
                ### Only check the last 4096 characters to avoid performance issues with large outputs
                tail = buffer[-4096:]
                if any(pattern.search(tail) for pattern in patterns):
                    return buffer

            ### If no pattern matched, read more data with a short timeout to allow for checking the deadline
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise asyncio.TimeoutError("Timed out waiting for prompt")

            ### Read the next chunk of output with a short timeout to allow for prompt detection
            chunk = await asyncio.wait_for(stream.read(256), timeout=min(remaining, 1.0))
            if chunk == "":
                return buffer

            ### Append the new chunk to the buffer and continue checking for patterns
            buffer += chunk
    async def _run_command_phase(
        self,
        process: asyncssh.SSHClientProcess,
        commands: list[dict[str, Any]],
        default_timeout: int,
        password: str,
        capture_output: bool,
        required: bool = True,
    ) -> list[dict[str, Any]]:
        """Run one command phase and return captured output chunks.

        Supported step types:
        - command (default): send `command` and optionally wait for prompt
        - send_input: send `input` text and optionally wait for prompt
                    (if `input` is omitted, device password is sent)

        A chunk contains:
        - command: command string
        - output: captured output text
        - comment: whether this output should be rendered as top comment block
        """
        captured_outputs: list[dict[str, Any]] = []

        for command_def in commands:
            ### Get type of the step
            step_type = str(command_def.get("type") or "command")
            step_type = step_type.strip().lower()

            comment = bool(command_def.get("comment", False))
            wait_for_prompt = bool(command_def.get("wait_for_prompt", True))

            ### Fire send input steps
            if step_type == "send_input":
                try:
                    ### Get input text and send it
                    input_text = password if command_def.get("input") is None else str(command_def.get("input"))
                    process.stdin.write(f"{input_text}\n")

                    ### Optionally wait for the prompt after sending input to ensure the device is ready for the next command
                    if wait_for_prompt:
                        await self._read_until_patterns(
                            process.stdout,
                            GENERIC_PROMPT_PATTERNS,
                            default_timeout,
                        )
                    else:
                        await asyncio.sleep(0.1)
                except Exception as ex:
                    if required:
                        raise RuntimeError("Step failed: send_input") from ex
                    logger.warning("Optional step failed 'send_input': %s", ex)
                continue

            ### Raise error for unsupported step types
            if step_type != "command":
                ex = ValueError(f"Unsupported command step type '{step_type}'")
                raise RuntimeError(str(ex)) from ex

            ### Fire command steps
            command = str(command_def.get("command") or "").strip()
            if not command:
                raise RuntimeError("Step failed: command is empty")

            try:
                output = await self._execute_shell_command(
                    process=process,
                    command=command,
                    timeout=default_timeout,
                    wait_for_prompt=wait_for_prompt,
                )
                if capture_output and output:
                    captured_outputs.append({
                        "command": command,
                        "output": output,
                        "comment": comment,
                    })
            except Exception as ex:
                if required:
                    raise RuntimeError(f"Command failed: {command}") from ex
                logger.warning("Optional command failed '%s': %s", command, ex)

        return captured_outputs
    async def connect(
        self,
        device: DeviceBase,
        username: str,
        password: str,
        *,
        ssh_profile: str,
        port: int = 22,
        timeout: int | None = None,
    ) -> asyncssh.SSHClientConnection:
        """Establish SSH connection to a device using configured profile options."""
        ssh_options = self._get_ssh_options(ssh_profile)

        ### Build asyncssh.connect kwargs, filtering out any None values
        connect_kwargs: dict[str, Any] = {
            "host": str(device.ip_address),
            "port": int(port),
            "username": username,
            "password": password,
            "known_hosts": ssh_options.get("known_hosts"),
            "kex_algs": ssh_options.get("kex_algs"),
            "encryption_algs": ssh_options.get("encryption_algs"),
            "server_host_key_algs": ssh_options.get("server_host_key_algs"),
            "connect_timeout": max(1, int(timeout)) if timeout is not None else None,
        }
        connect_kwargs = {key: value for key, value in connect_kwargs.items() if value is not None}

        logger.debug(
            "Opening SSH connection to %s (%s:%d) with profile '%s'",
            device.device_name,
            device.ip_address,
            int(port),
            ssh_profile,
        )
        return await asyncssh.connect(**connect_kwargs)

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
