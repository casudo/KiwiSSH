"""SSH connection service using asyncssh."""

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

import asyncssh

from app.models.device import DeviceBase
from app.services.cli_service import (
    ANSI_ESCAPE_RE,
    READ_CHUNK_SIZE,
    READ_POLL_INTERVAL_SECONDS,
    CLIService,
    CLISession,
    PaginationRule,
)
from app.services.protocol_common import fetch_with_retries

logger = logging.getLogger(__name__)


class SSHShellSession(CLISession):
    """Interactive shell of an SSH connection."""

    def __init__(self, process: asyncssh.SSHClientProcess) -> None:
        self.process = process

    async def read(self, size: int) -> str:
        return await self.process.stdout.read(size)

    async def write(self, data: str) -> None:
        self.process.stdin.write(data)

    async def close(self) -> None:
        """Force-close the local shell handle; the SSH connection itself is closed by the caller."""
        forced_close_wait_timeout_seconds = 1.5
        try:
            close = getattr(self.process, "close", None)
            if callable(close):
                close()
            else:
                channel = getattr(self.process, "channel", None)
                if channel is None and hasattr(self.process, "stdin"):
                    channel = getattr(self.process.stdin, "channel", None)
                if channel is not None:
                    channel.close()
        except Exception as ex:
            logger.debug(
                "Forced shell close failed (%s: %s); continuing outer SSH connection cleanup",
                ex.__class__.__name__,
                ex,
            )

        wait_closed = getattr(self.process, "wait_closed", None)
        if callable(wait_closed):
            try:
                await asyncio.wait_for(wait_closed(), timeout=forced_close_wait_timeout_seconds)
            except Exception:
                pass


class SSHService(CLIService):
    """Service for SSH connections to network devices."""

    PROTOCOL = "ssh"
    PROTOCOL_LABEL = "SSH"

    def _get_ssh_options(self, profile_name: str) -> dict[str, Any]:
        """Get SSH options from profile and map known_hosts policy."""
        profile = self.settings.get_ssh_profile(profile_name)
        if not isinstance(profile, dict):
            raise ValueError(f"SSH profile '{profile_name}' not found")

        policy = str(profile.get("known_hosts_policy", "ignore")).lower().strip()
        if policy == "strict":
            known_hosts: str | None = str(Path.home() / ".ssh" / "known_hosts")
        else:
            if policy == "auto_add":
                logger.warning(
                    "known_hosts_policy 'auto_add' is not implemented; falling back to 'ignore'"
                )
                ### TODO: Implement auto_add
            known_hosts = None # None is AsyncSSH's way of disabling host key checks aka ignore mode

        ### Map configured SSH profile options to asyncssh.connect kwargs
        return {
            "kex_algs": profile.get("kex_algorithms"),
            "encryption_algs": profile.get("ciphers"),
            "server_host_key_algs": profile.get("host_key_algorithms"),
            "known_hosts": known_hosts,
        }

    @staticmethod
    def _resolve_client_key_path(ssh_key_file: str | None) -> str | None:
        """Resolve and normalize configured SSH key file path for AsyncSSH."""
        if ssh_key_file is None:
            return None

        normalized = str(ssh_key_file).strip()
        if not normalized:
            return None

        ### Expand '~' for local/bare-metal usage while preserving absolute paths..
        ## ..used inside containers (for example '/home/kiwissh/.ssh/id_ed25519')
        return str(Path(normalized).expanduser())

    async def _run_session_login(
        self,
        session: CLISession,
        login_steps: list[dict[str, Any]],
        *,
        username: str,
        password: str | None,
        timeout: int,
        pagination_rules: list[PaginationRule] | None = None,
    ) -> None:
        """Run an optional vendor-defined interactive login inside the SSH shell.

        Some devices do not present a CLI prompt right after the SSH connection is established and instead require an additional in-shell login.
        https://github.com/casudo/KiwiSSH/issues/55

        Each step waits for its `expect` regex to appear, then sends the configured `send` value.
        The placeholders '{{ username }}' and '{{ password }}' are replaced with the device credentials specified per group/node.

        While waiting, prompts matching the vendor's pagination rules (e.g. "Press <Enter> to continue") are answered.
        """
        placeholders = {
            "{{ username }}": username,
            "{{ password }}": password or "",
        }

        loop = asyncio.get_running_loop()
        timeout_seconds = max(1, int(timeout))

        for index, step in enumerate(login_steps, start=1):
            if not isinstance(step, dict):
                raise RuntimeError(
                    f"session.login step #{index} must be a mapping with 'expect' and 'send'"
                )

            ### Validate "expect" pattern is present and valid
            expect = str(step.get("expect") or "").strip()
            if not expect:
                raise RuntimeError(
                    f"session.login step #{index} requires a non-empty 'expect' pattern"
                )
            try:
                expect_pattern = re.compile(expect)
            except re.error as ex:
                raise RuntimeError(
                    f"Invalid session.login expect pattern '{expect}': {ex}"
                ) from ex

            ### Read until the "expect" prompt appears or the timeout is reached
            deadline = loop.time() + timeout_seconds
            buffer = ""
            while True:
                visible = ANSI_ESCAPE_RE.sub("", buffer)
                if expect_pattern.search(visible):
                    break

                ### Answer interim prompts like "Press <Enter> to continue" with the vendor's pagination response
                lines = [line for line in visible.replace("\r", "").split("\n") if line.strip()]
                pagination_response = (
                    self._match_pagination_response(lines[-1], pagination_rules)
                    if lines and pagination_rules
                    else None
                )
                if pagination_response is not None:
                    await session.write(pagination_response)
                    buffer = ""
                    deadline = loop.time() + timeout_seconds
                    continue

                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise asyncio.TimeoutError(
                        f"Timed out waiting for session.login pattern '{expect}'"
                    )
                try:
                    chunk = await asyncio.wait_for(
                        session.read(READ_CHUNK_SIZE),
                        timeout=min(remaining, READ_POLL_INTERVAL_SECONDS),
                    )
                except asyncio.TimeoutError:
                    continue
                if chunk == "":
                    raise RuntimeError(
                        f"SSH shell closed while waiting for session.login pattern '{expect}'"
                    )
                buffer += chunk

            ### Resolve the value to send, substituting credential placeholders
            send_template = str(step.get("send") or "")
            send_value = placeholders.get(send_template.strip(), send_template)
            payload = send_value if send_value.endswith(("\n", "\r")) else f"{send_value}\n"
            await session.write(payload)

    async def _prepare_session(
        self,
        session: CLISession,
        vendor_id: str,
        session_config: dict[str, Any],
        prompt_patterns: list[re.Pattern[str]],
        *,
        username: str,
        password: str | None,
        timeout: int,
    ) -> None:
        """Run the vendor's optional interactive in-shell login before anything else."""
        ## https://github.com/casudo/KiwiSSH/issues/55
        login_steps = session_config.get("login") or [] # Optional interactive in-shell login sequence
        if login_steps and not isinstance(login_steps, list):
            raise RuntimeError(f"Vendor '{vendor_id}' session.login must be a list of steps")
        if login_steps:
            await self._run_session_login(
                session,
                login_steps,
                username=username,
                password=password,
                timeout=timeout,
                pagination_rules=self._get_pagination_settings(vendor_id),
            )

    async def connect(
        self,
        host: str,
        username: str,
        *,
        ssh_profile: str,
        password: str | None = None,
        ssh_key_file: str | None = None,
        port: int = 22,
        timeout: int | None = None,
        tunnel: asyncssh.SSHClientConnection | None = None,
        connection_label: str | None = None,
    ) -> asyncssh.SSHClientConnection:
        """Establish SSH connection using password and/or client key authentication."""
        ### Normalize required values early to provide clear error messages
        normalized_host = str(host).strip()
        normalized_username = str(username).strip()
        normalized_password = str(password).strip() if password is not None else ""
        normalized_key_file = self._resolve_client_key_path(ssh_key_file)

        if not normalized_host:
            raise ValueError("SSH host must be a non-empty string")
        if not normalized_username:
            raise ValueError("SSH username must be a non-empty string")

        ### Enforce at least one auth method
        if not normalized_password and not normalized_key_file:
            raise ValueError("SSH connection requires either password or ssh_key_file")

        ssh_options = self._get_ssh_options(ssh_profile)

        ### Build asyncssh.connect kwargs
        ## IMPORTANT: keep known_hosts=None for ignore mode. If omitted, AsyncSSH falls back..
        ## ..to strict host-key checks against ~/.ssh/known_hosts
        connect_kwargs: dict[str, Any] = {
            "host": normalized_host,
            "port": int(port),
            "username": normalized_username,
            "known_hosts": ssh_options.get("known_hosts"),
            "preferred_auth": ["keyboard-interactive", "password", "publickey"],
        }

        ### Add password auth only when configured
        if normalized_password:
            connect_kwargs["password"] = normalized_password

        ### Add key-based auth when a key file is configured
        if normalized_key_file:
            connect_kwargs["client_keys"] = [normalized_key_file]

        ### Tunnel is used for jumphost chaining:
        ### device connection goes through an already-open jumphost session
        if tunnel is not None:
            connect_kwargs["tunnel"] = tunnel

        optional_kwargs: dict[str, Any] = {
            "kex_algs": ssh_options.get("kex_algs"),
            "encryption_algs": ssh_options.get("encryption_algs"),
            "server_host_key_algs": ssh_options.get("server_host_key_algs"),
            "connect_timeout": max(1, int(timeout)) if timeout is not None else None,
        }
        for key, value in optional_kwargs.items():
            if value is not None:
                connect_kwargs[key] = value

        label = connection_label or normalized_host
        logger.debug(
            "Opening SSH connection to %s (%s:%d) with profile '%s'",
            label,
            normalized_host,
            int(port),
            ssh_profile,
        )
        return await asyncssh.connect(**connect_kwargs)

    async def get_config(
        self,
        device: DeviceBase,
        *,
        device_config: dict[str, Any] | None = None,
    ) -> tuple[str, str | None]:
        """Get device configuration plus optional metadata via SSH."""
        ### Get device config
        device_config = device_config or self.settings.get_device_config(device.group, device.device_name)
        enable_password_raw = str(device_config.get("enable_password") or "").strip()
        enable_password = enable_password_raw if enable_password_raw else None
        redaction = device_config.get("redaction") # group/node override (none keeps the vendors default)

        protocol = str(device_config.get("protocol")).strip().lower()
        if protocol != "ssh":
            raise ValueError(
                f"Device '{device.device_name}' in group '{device.group}' requires SSH protocol for ssh_service.py"
            )

        ### Filter for required SSH config values
        timeout_seconds = int(device_config["timeout"])
        retry_count = int(device_config["retry"])
        vendor_id = str(device_config["vendor"]).strip()
        device_ssh_profile = str(device_config["ssh_profile"]).strip()
        device_port = int(device_config.get("port") or 22)
        device_username = str(device_config["username"]).strip()

        ### Device authentication can be password-based, key-based, or both.
        device_password_raw = str(device_config.get("password") or "").strip()
        device_password = device_password_raw if device_password_raw else None
        device_key_file_raw = str(device_config.get("ssh_key_file") or "").strip()
        device_ssh_key_file = device_key_file_raw if device_key_file_raw else None

        ### Jumphost settings are optional and already validated in get_device_config
        jumphost_cfg = device_config.get("jumphost")

        async def fetch_once() -> tuple[str, str | None]:
            """One connection attempt running the commands defined in vendor YAML."""
            jump_connection: asyncssh.SSHClientConnection | None = None
            connection: asyncssh.SSHClientConnection | None = None
            try:
                ### If jumphost is configured, open it first and tunnel the..
                ## ..device SSH connection through that session
                if jumphost_cfg:
                    jumphost_name = str(jumphost_cfg.get("hostname") or "").strip()
                    jumphost_port = int(jumphost_cfg.get("port") or 22)
                    jumphost_username = str(jumphost_cfg.get("username") or "").strip()
                    jumphost_ssh_profile = str(jumphost_cfg.get("ssh_profile") or "").strip()

                    jumphost_password_raw = str(jumphost_cfg.get("password") or "").strip()
                    jumphost_password = jumphost_password_raw if jumphost_password_raw else None
                    jumphost_key_raw = str(jumphost_cfg.get("ssh_key_file") or "").strip()
                    jumphost_ssh_key_file = jumphost_key_raw if jumphost_key_raw else None

                    logger.debug(
                        "Connecting to jumphost '%s' for device '%s'",
                        jumphost_name,
                        device.device_name,
                    )
                    jump_connection = await self.connect(
                        host=jumphost_name,
                        port=jumphost_port,
                        username=jumphost_username,
                        password=jumphost_password,
                        ssh_key_file=jumphost_ssh_key_file,
                        ssh_profile=jumphost_ssh_profile,
                        timeout=timeout_seconds,
                        connection_label=f"jumphost:{jumphost_name}",
                    )

                ### Connect via SSH using SSH profile options
                connection = await self.connect(
                    host=str(device.ip_address),
                    username=device_username,
                    password=device_password,
                    ssh_key_file=device_ssh_key_file,
                    port=device_port,
                    ssh_profile=device_ssh_profile,
                    timeout=timeout_seconds,
                    tunnel=jump_connection,
                    connection_label=device.device_name,
                )

                ### Fun part: Run the configured command phases to capture device config
                process = await connection.create_process(term_type="vt100", encoding="utf-8")
                return await self._collect_vendor_config(
                    SSHShellSession(process),
                    vendor_id=vendor_id,
                    default_timeout=timeout_seconds,
                    enable_password=enable_password,
                    username=device_username, # used for interactive in-shell login steps
                    password=device_password, # used for interactive in-shell login steps
                    redaction=redaction,
                )
            finally:
                ### Ensure connection is properly closed to avoid resource leaks, even on failure
                if connection is not None:
                    connection.close()
                    try:
                        await connection.wait_closed()
                    except Exception:
                        pass

                ### Always close jumphost tunnel after device connection closes
                if jump_connection is not None:
                    jump_connection.close()
                    try:
                        await jump_connection.wait_closed()
                    except Exception:
                        pass

        ### Try to fetch config from device, applying retries on failure
        return await fetch_with_retries(
            device,
            fetch_once,
            max_attempts=retry_count + 1,
            timeout_seconds=timeout_seconds,
            protocol_label=self.PROTOCOL_LABEL,
        )


### Singleton instance
ssh_service = SSHService()
