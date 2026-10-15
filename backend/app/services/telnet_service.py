"""Telnet connection service using telnetlib3."""

import asyncio
import contextlib
import logging
import re
import inspect
from typing import Any

import telnetlib3

from app.models.device import DeviceBase
from app.services.cli_service import READ_CHUNK_SIZE, READ_POLL_INTERVAL_SECONDS, CLIService, CLISession
from app.services.protocol_common import fetch_with_retries

logger = logging.getLogger(__name__)

LOGIN_USERNAME_PATTERNS = [
    re.compile(r"(?:login|username)\s*[:>]\s*$", re.IGNORECASE),
    re.compile(r"user\s*name\s*[:>]\s*$", re.IGNORECASE),
]
LOGIN_PASSWORD_PATTERNS = [
    re.compile(r"password\s*[:>]\s*$", re.IGNORECASE),
]


class TelnetSession(CLISession):
    """Interactive shell of a Telnet connection."""

    def __init__(self, reader: Any, writer: Any) -> None:
        self.reader = reader
        self.writer = writer

    async def read(self, size: int) -> str:
        return await self.reader.read(size)

    async def write(self, data: str) -> None:
        """Write data to the Telnet session.

        Raises:
            ConnectionError: If the Telnet protocol is closed.
        """
        try:
            self.writer.write(data)
            drain = getattr(self.writer, "drain", None)
            if callable(drain):
                await drain()
        except Exception as ex:
            raise ConnectionError("Telnet protocol is closed") from ex

    async def close(self) -> None:
        ### Attempt graceful close if the writer supports it
        close = getattr(self.writer, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass

        ### Wait for the connection to fully close before the next retry attempt to avoid overlapping sessions
        ### Use a short grace period and skip if the close future is on a different loop
        await self._safe_wait_closed(self.writer, timeout=1.5)

    @staticmethod
    async def _safe_wait_closed(writer: Any, timeout: float) -> None:
        """Wait for writer close, skipping futures bound to a different loop."""
        wait_closed = getattr(writer, "wait_closed", None)
        if not callable(wait_closed):
            return

        try:
            result = wait_closed()
        except Exception:
            return

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if isinstance(result, asyncio.Future):
            ### Avoid cross-loop futures which raise "attached to a different loop"
            if running_loop is not None and result.get_loop() is not running_loop:
                return
            try:
                await asyncio.wait_for(result, timeout=timeout)
            except RuntimeError as ex:
                if "attached to a different loop" in str(ex):
                    return
                raise
            except Exception:
                return
            return

        if inspect.iscoroutine(result):
            ### Some telnetlib3 versions return a coroutine instead of a Future
            try:
                await asyncio.wait_for(result, timeout=timeout)
            except RuntimeError as ex:
                if "attached to a different loop" in str(ex):
                    return
                raise
            except Exception:
                return
            return


class TelnetService(CLIService):
    """Service for Telnet connections to network devices."""

    PROTOCOL = "telnet"
    PROTOCOL_LABEL = "Telnet"

    @staticmethod
    def _build_open_connection_kwargs(
        host: str,
        port: int,
        timeout: int,
        loop: asyncio.AbstractEventLoop,
    ) -> dict[str, Any]:
        """Build telnetlib3.open_connection kwargs with signature guards."""
        kwargs: dict[str, Any] = {
            "host": host,
            "port": port,
            "encoding": "utf-8",
        }

        try:
            signature = inspect.signature(telnetlib3.open_connection)
            params = signature.parameters
        except (TypeError, ValueError):
            params = {}

        if "connect_minwait" in params:
            kwargs["connect_minwait"] = 0.2
        if "connect_maxwait" in params:
            kwargs["connect_maxwait"] = max(1, timeout)
        if "loop" in params:
            kwargs["loop"] = loop

        return kwargs

    async def _login(
        self,
        session: CLISession,
        username: str,
        password: str,
        prompt_patterns: list[re.Pattern[str]],
        timeout: int,
    ) -> None:
        """Handle basic Telnet login prompts (username/password)."""
        ### Send a 'enter' to the session so the device prints a banner or prompt
        await session.write("\n")
        loop = asyncio.get_running_loop()
        timeout_seconds = max(1, int(timeout))
        inactivity_deadline = loop.time() + timeout_seconds
        buffer = ""
        ### Track whether we've already sent credentials to avoid repeats
        sent_username = False
        sent_password = False

        while True:
            tail = buffer[-4096:]
            tail_lines = tail.split("\n")
            while tail_lines and not tail_lines[-1].strip():
                tail_lines.pop()

            ### If we hit a shell prompt, we're successfully logged in
            if tail_lines and self._line_matches_prompt(tail_lines[-1], prompt_patterns):
                return

            ### Send username on username prompts
            if tail_lines and not sent_username and self._line_matches_any(tail_lines[-1], LOGIN_USERNAME_PATTERNS):
                await session.write(f"{username}\n")
                sent_username = True
                buffer = ""
                inactivity_deadline = loop.time() + timeout_seconds
                continue

            ### Send password on password prompts
            if tail_lines and not sent_password and self._line_matches_any(tail_lines[-1], LOGIN_PASSWORD_PATTERNS):
                await session.write(f"{password}\n")
                sent_password = True
                buffer = ""
                inactivity_deadline = loop.time() + timeout_seconds
                continue

            remaining = inactivity_deadline - loop.time()
            if remaining <= 0:
                raise asyncio.TimeoutError("Timed out waiting for Telnet login prompt")

            try:
                chunk = await asyncio.wait_for(
                    session.read(READ_CHUNK_SIZE),
                    timeout=min(remaining, READ_POLL_INTERVAL_SECONDS),
                )
            except asyncio.TimeoutError:
                continue

            if chunk == "":
                return

            buffer += chunk
            inactivity_deadline = loop.time() + timeout_seconds

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
        """Answer the device's username/password prompts before running any commands."""
        await self._login(
            session,
            username=username,
            password=password or "",
            prompt_patterns=prompt_patterns,
            timeout=timeout,
        )

    async def get_config(
        self,
        device: DeviceBase,
        *,
        device_config: dict[str, Any] | None = None,
    ) -> tuple[str, str | None]:
        """Get device configuration plus optional metadata via Telnet or local simulator."""
        ### Get device config
        device_config = device_config or self.settings.get_device_config(device.group, device.device_name)
        enable_password_raw = str(device_config.get("enable_password") or "").strip()
        enable_password = enable_password_raw if enable_password_raw else None

        protocol = str(device_config.get("protocol") or "ssh").strip().lower()
        if protocol != "telnet":
            raise ValueError(
                f"Device '{device.device_name}' in group '{device.group}' requires Telnet protocol for telnet_service.py"
            )

        ### Filter for required Telnet config values
        timeout_seconds = int(device_config["timeout"])
        retry_count = int(device_config["retry"])
        vendor_id = str(device_config["vendor"]).strip()
        device_port = int(device_config.get("port") or 23)
        device_username = str(device_config["username"]).strip()

        ### Device authentication can be password-based only for Telnet
        device_password_raw = str(device_config.get("password") or "").strip()
        device_password = device_password_raw if device_password_raw else None
        if not device_password:
            raise ValueError(
                f"Device '{device.device_name}' in group '{device.group}' requires password for telnet protocol"
            )

        ### Use the local simulator if test mode is enabled
        if self.settings.local_test_mode:
            return await self._collect_local_vendor_config(
                device=device,
                vendor_id=vendor_id,
                timeout_seconds=timeout_seconds,
            )

        async def fetch_once() -> tuple[str, str | None]:
            """One connection attempt running the commands defined in vendor YAML."""
            session: TelnetSession | None = None
            try:
                loop = asyncio.get_running_loop()
                asyncio.set_event_loop(loop)
                connect_kwargs = self._build_open_connection_kwargs(
                    host=str(device.ip_address),
                    port=device_port,
                    timeout=timeout_seconds,
                    loop=loop,
                )

                ### Connect via Telnet
                connect_task = asyncio.create_task(telnetlib3.open_connection(**connect_kwargs))
                try:
                    reader, writer = await asyncio.wait_for(
                        connect_task,
                        timeout=max(2, timeout_seconds),
                    )
                except asyncio.TimeoutError:
                    connect_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await connect_task
                    raise
                session = TelnetSession(reader, writer)

                ### Fun part: Log in and run the configured command phases to capture device config
                return await self._collect_vendor_config(
                    session,
                    vendor_id=vendor_id,
                    default_timeout=timeout_seconds,
                    enable_password=enable_password,
                    username=device_username,
                    password=device_password,
                )
            finally:
                ### Ensure connection is properly closed to avoid resource leaks, even on failure
                if session is not None:
                    await session.close()

        ### Try to fetch config from device, applying retries on failure
        return await fetch_with_retries(
            device,
            fetch_once,
            max_attempts=retry_count + 1,
            timeout_seconds=timeout_seconds,
            protocol_label=self.PROTOCOL_LABEL,
        )


### Singleton instance
telnet_service = TelnetService()
