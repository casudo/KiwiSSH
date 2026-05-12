"""Telnet connection service using telnetlib3."""

import asyncio
import contextlib
import logging
import re
import inspect
from typing import Any

import telnetlib3

from app.core import get_settings
from app.models.device import DeviceBase
from app.services.vendor_service import vendor_service
from app.services.local_ssh_simulator import local_ssh_simulator
from app.services.ssh_service import (
    ANSI_ESCAPE_RE,
    DEFAULT_PAGINATION_PATTERNS,
    DEFAULT_PAGINATION_RESPONSE,
    GENERIC_PROMPT_PATTERNS,
    LARGE_OUTPUT_INACTIVITY_TIMEOUT_SECONDS,
    LARGE_OUTPUT_TIMEOUT_THRESHOLD_BYTES,
    PROMPT_CONFIRM_IDLE_SECONDS,
    PROMPT_CONFIRM_MAX_SECONDS,
    READ_CHUNK_SIZE,
    READ_POLL_INTERVAL_SECONDS,
)

logger = logging.getLogger(__name__)

LOGIN_USERNAME_PATTERNS = [
    re.compile(r"(?:login|username)\s*[:>]\s*$", re.IGNORECASE),
    re.compile(r"user\s*name\s*[:>]\s*$", re.IGNORECASE),
]
LOGIN_PASSWORD_PATTERNS = [
    re.compile(r"password\s*[:>]\s*$", re.IGNORECASE),
]

PaginationRule = tuple[re.Pattern[str], str]


class TelnetService:
    """Service for Telnet connections to network devices."""

    def __init__(self) -> None:
        self.settings = get_settings()

    @staticmethod
    def _line_matches_prompt(
        line: str,
        patterns: list[re.Pattern[str]],
    ) -> bool:
        """Check whether a line matches any configured prompt pattern."""
        normalized_line = ANSI_ESCAPE_RE.sub("", line).replace("\r", "").replace("\x08", "")
        return any(pattern.fullmatch(normalized_line) for pattern in patterns)

    @staticmethod
    def _line_matches_any(line: str, patterns: list[re.Pattern[str]]) -> bool:
        """Check whether a line matches any configured regex patterns."""
        normalized_line = ANSI_ESCAPE_RE.sub("", line).replace("\r", "").replace("\x08", "")
        return any(pattern.search(normalized_line) for pattern in patterns)

    def _get_prompt_patterns(self, vendor_id: str) -> list[re.Pattern[str]]:
        """Get prompt patterns from vendor session config with generic fallback."""
        session_config = vendor_service.get_session_parameters(vendor_id)
        prompt_config = session_config.get("prompt")

        ### Use default if not explicitly set
        if prompt_config is None:
            return GENERIC_PROMPT_PATTERNS

        ### Read from session.prompt
        prompt_values: list[str]
        if isinstance(prompt_config, str):
            prompt_values = [prompt_config]
        elif isinstance(prompt_config, list):
            prompt_values = [str(value) for value in prompt_config if str(value).strip()]
        else:
            logger.warning(
                "Invalid session.prompt for vendor '%s': expected string or list; using generic prompt pattern",
                vendor_id,
            )
            return GENERIC_PROMPT_PATTERNS

        ### Check if the given regex is valid
        compiled_patterns: list[re.Pattern[str]] = []
        for prompt_value in prompt_values:
            try:
                compiled_patterns.append(re.compile(prompt_value))
            except re.error as ex:
                logger.warning(
                    "Invalid session.prompt regex '%s' for vendor '%s': %s",
                    prompt_value,
                    vendor_id,
                    ex,
                )

        if compiled_patterns:
            ### Keep generic defaults as fallback for uncovered prompt variants
            ## compiled_patterns are used FIRST before default patterns
            generic_fallback = [
                pattern
                for pattern in GENERIC_PROMPT_PATTERNS
                if all(pattern.pattern != configured.pattern for configured in compiled_patterns)
            ]
            return compiled_patterns + generic_fallback

        logger.warning(
            "No valid session.prompt patterns for vendor '%s'; using generic prompt pattern",
            vendor_id,
        )
        return GENERIC_PROMPT_PATTERNS

    def _get_pagination_settings(self, vendor_id: str) -> list[PaginationRule]:
        """Get optional pagination detection rules from vendor session config."""
        session_config = vendor_service.get_session_parameters(vendor_id)
        pagination_config = session_config.get("pagination")

        ### Default: handle common pagination markers even when vendor config doesn't define pagination settings
        if pagination_config is None:
            return [(pattern, DEFAULT_PAGINATION_RESPONSE) for pattern in DEFAULT_PAGINATION_PATTERNS]

        if not isinstance(pagination_config, dict):
            logger.warning(
                "Invalid session.pagination for vendor '%s': expected mapping; disabling pagination handling",
                vendor_id,
            )
            return []

        if not bool(pagination_config.get("enabled", False)):
            return []

        raw_patterns = pagination_config.get("patterns", [])

        ### Check for single or multiple pagination patterns and normalize to a list
        pattern_items: list[Any]
        if isinstance(raw_patterns, str):
            pattern_items = [raw_patterns]
        elif isinstance(raw_patterns, list):
            pattern_items = list(raw_patterns)
        else:
            logger.warning(
                "Invalid session.pagination.patterns for vendor '%s': expected string or list; disabling pagination handling",
                vendor_id,
            )
            return []

        ### If no patterns avaialble after normalization, fall back to built-in defaults
        if not pattern_items:
            return [(pattern, DEFAULT_PAGINATION_RESPONSE) for pattern in DEFAULT_PAGINATION_PATTERNS]

        ### Validate pagination regex patterns and bind each to a response
        compiled_rules: list[PaginationRule] = []
        for pattern_item in pattern_items:
            response = DEFAULT_PAGINATION_RESPONSE

            if isinstance(pattern_item, dict):
                raw_pattern = pattern_item.get("pattern")
                if pattern_item.get("response") is not None:
                    configured_response = str(pattern_item.get("response"))
                    response = configured_response if configured_response else DEFAULT_PAGINATION_RESPONSE
            else:
                raw_pattern = pattern_item

            pattern_value = "" if raw_pattern is None else str(raw_pattern).strip()
            if not pattern_value:
                logger.warning(
                    "Invalid empty session.pagination.patterns entry for vendor '%s'; skipping",
                    vendor_id,
                )
                continue

            try:
                compiled_rules.append((re.compile(pattern_value), response))
            except re.error as ex:
                logger.warning(
                    "Invalid session.pagination regex pattern '%s' for vendor '%s': %s",
                    pattern_value,
                    vendor_id,
                    ex,
                )

        ### Fall back to defaults if no compiled patterns
        if not compiled_rules:
            logger.warning(
                "No valid session.pagination patterns for vendor '%s'; falling back to built-in defaults",
                vendor_id,
            )
            return [(pattern, DEFAULT_PAGINATION_RESPONSE) for pattern in DEFAULT_PAGINATION_PATTERNS]

        ### Keep generic defaults as fallback for uncovered pagination variants
        ## compiled_rules are used FIRST before default patterns
        return compiled_rules + [
            (pattern, DEFAULT_PAGINATION_RESPONSE)
            for pattern in DEFAULT_PAGINATION_PATTERNS
        ]

    @staticmethod
    def _match_pagination_response(
        line: str,
        rules: list[PaginationRule],
    ) -> str | None:
        """Return the response for the first matching pagination rule, if any."""
        normalized_line = ANSI_ESCAPE_RE.sub("", line).replace("\r", "").replace("\x08", "")
        for pattern, response in rules:
            if pattern.search(normalized_line):
                return response
        return None

    @staticmethod
    async def _write(writer: Any, data: str) -> None:
        """Write data to the Telnet session.

        Args:
            writer (Any): The Telnet writer object.
            data (str): The data to write, typically a command or response.

        Raises:
            ConnectionError: If the Telnet protocol is closed.
        """
        try:
            writer.write(data)
            drain = getattr(writer, "drain", None)
            if callable(drain):
                await drain()
        except Exception as ex:
            raise ConnectionError("Telnet protocol is closed") from ex

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

    @staticmethod
    def _build_metadata_section(
        captured_output: list[dict[str, Any]],
        comment_prefix: str,
    ) -> str:
        """Render metadata-marked command outputs."""
        lines: list[str] = []

        for chunk in captured_output:
            ### Only chunks marked with metadata=true are rendered in this section
            if not bool(chunk.get("metadata", False)):
                continue

            command = str(chunk.get("command", "")).strip()
            output = str(chunk.get("output", "")).strip("\n")
            ### Skip empty output blocks to avoid noisy placeholders
            if not output:
                continue

            ### Create header line for the command, prefixed with the vendor's comment marker
            lines.append(f"{comment_prefix}Command used: {command}")

            ### Prefix each output line with the vendor comment marker
            ### For blank lines, keep only the prefix without trailing spaces
            for output_line in output.splitlines():
                lines.append(f"{comment_prefix}{output_line}" if output_line else comment_prefix.rstrip())

            ### Add a blank comment line between command blocks
            lines.append(comment_prefix.rstrip())

        ### Trim outer newlines but preserve internal block spacing
        return "\n".join(lines).strip("\n")

    async def _read_until_patterns(
        self,
        reader: Any,
        patterns: list[re.Pattern[str]],
        timeout: int,
        *,
        writer: Any | None = None,
        pagination_rules: list[PaginationRule] | None = None,
    ) -> str:
        """Read stream until one of the patterns appears or timeout is reached."""
        loop = asyncio.get_running_loop()
        timeout_seconds = max(1, int(timeout))
        inactivity_deadline = loop.time() + timeout_seconds
        buffer = ""
        resolved_pagination_rules = pagination_rules or []

        ### Read in a loop until we see a prompt pattern or hit the timeout
        while True:
            ### Check if any prompt pattern matches the current output line
            ## Evaluating only the last line avoids false positives from earlier content..
            ## ..and from random chunk boundaries inside large command outputs
            if patterns:
                tail = buffer[-4096:]
                tail_lines = tail.split("\n")

                ### Some devices return a newline right after the command output
                ## Use the last non-empty line so prompt detection remains reliable
                while tail_lines and not tail_lines[-1].strip():
                    tail_lines.pop()

                if tail_lines and self._line_matches_prompt(tail_lines[-1], patterns):
                    ### Confirm prompt by waiting for a short idle window
                    ### If more output arrives, treat it as a false prompt match and keep reading
                    idle_timeout = PROMPT_CONFIRM_IDLE_SECONDS
                    max_total_seconds = PROMPT_CONFIRM_MAX_SECONDS
                    if len(buffer) >= LARGE_OUTPUT_TIMEOUT_THRESHOLD_BYTES:
                        # Allow a longer quiet window to catch late chunks from large outputs.
                        idle_timeout = max(idle_timeout, 0.4)
                        max_total_seconds = max(max_total_seconds, 4.0)
                    trailing = await self._read_trailing_output(
                        reader,
                        idle_timeout=idle_timeout,
                        max_chunks=None,
                        max_total_seconds=max_total_seconds,
                    )
                    if trailing:
                        buffer += trailing
                        continue
                    return buffer

                ### Handle pagination prompts by sending the response for the matching pagination rule
                matched_pagination_response = None
                if tail_lines and resolved_pagination_rules:
                    matched_pagination_response = self._match_pagination_response(
                        tail_lines[-1],
                        resolved_pagination_rules,
                    )

                if matched_pagination_response is not None:
                    if writer is not None:
                        await self._write(writer, matched_pagination_response)

                    ### After sending pagination continuation, wait another full timeout window
                    inactivity_deadline = loop.time() + timeout_seconds

                    ### Remove pagination marker line from captured output to avoid noisy backups
                    if "\n" in buffer:
                        buffer = f"{buffer.rsplit('\n', 1)[0]}\n"
                    else:
                        buffer = ""
                    continue

            ### If no pattern matched, read more data with a short timeout to allow for checking the deadline
            remaining = inactivity_deadline - loop.time()
            if remaining <= 0:
                ### Check last 1024 bytes for a non-empty line to include in the timeout log
                timeout_tail = buffer[-1024:]
                timeout_lines = timeout_tail.split("\n")
                last_non_empty = ""
                while timeout_lines:
                    candidate = timeout_lines.pop().strip("\r")
                    if candidate.strip():
                        last_non_empty = candidate
                        break

                logger.debug(
                    "Timed out waiting for prompt. Last non-empty output line: %r",
                    ANSI_ESCAPE_RE.sub("", last_non_empty)[-200:],
                )
                raise asyncio.TimeoutError("Timed out waiting for prompt")

            ### Read the next chunk of output with a short timeout to allow for prompt detection
            try:
                chunk = await asyncio.wait_for(
                    reader.read(READ_CHUNK_SIZE),
                    timeout=min(remaining, READ_POLL_INTERVAL_SECONDS),
                )
            except asyncio.TimeoutError:
                ### No new bytes in this polling window; keep waiting until overall deadline
                continue

            if chunk == "":
                return buffer

            ### Append the new chunk to the buffer and continue checking for patterns
            buffer += chunk

            ### Large outputs on slower devices can pause for longer between chunks
            if (
                len(buffer) >= LARGE_OUTPUT_TIMEOUT_THRESHOLD_BYTES
                and timeout_seconds < LARGE_OUTPUT_INACTIVITY_TIMEOUT_SECONDS
            ):
                timeout_seconds = LARGE_OUTPUT_INACTIVITY_TIMEOUT_SECONDS
                logger.debug(
                    "Extended prompt inactivity timeout to %ds for large output stream (%d bytes buffered)",
                    timeout_seconds,
                    len(buffer),
                )

            ### Timeout tracks inactivity, not total command runtime
            inactivity_deadline = loop.time() + timeout_seconds

    @staticmethod
    async def _read_trailing_output(
        reader: Any,
        idle_timeout: float = 0.05,
        max_chunks: int | None = 16,
        max_total_seconds: float | None = None,
    ) -> str:
        """Read immediately available trailing output after prompt detection."""
        loop = asyncio.get_running_loop()
        start_time = loop.time()
        trailing = ""
        chunks_read = 0
        while True:
            if max_chunks is not None and chunks_read >= max_chunks:
                break
            if max_total_seconds is not None and (loop.time() - start_time) >= max_total_seconds:
                break
            try:
                chunk = await asyncio.wait_for(reader.read(READ_CHUNK_SIZE), timeout=idle_timeout)
            except asyncio.TimeoutError:
                break

            if chunk == "":
                break

            trailing += chunk
            chunks_read += 1

        return trailing

    @staticmethod
    def _sanitize_command_output(
        raw_output: str,
        command: str,
        prompt_patterns: list[re.Pattern[str]],
        known_commands: list[str] | None = None,
    ) -> str:
        """Normalize interactive shell output and strip prompt/command echo."""
        ### Strip terminal control sequences and normalize line endings/backspaces.
        text = ANSI_ESCAPE_RE.sub("", raw_output)
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x08", "")

        ### Process text as lines so we can remove common shell noise deterministically.
        lines = text.split("\n")

        ### Drop leading blank lines before the command output starts.
        while lines and not lines[0].strip():
            lines.pop(0)

        ### Remove command echo and any stale lines before it in early output.
        command_text = command.strip()
        command_echo_index: int | None = None
        for index, line in enumerate(lines[:8]):
            stripped_line = line.strip()
            if not stripped_line:
                continue
            if stripped_line == command_text:
                command_echo_index = index
                break
            if re.search(rf"[>#]\s*{re.escape(command_text)}\s*$", stripped_line):
                ### Some devices echo commands as '<prompt><command>' in the output.
                command_echo_index = index
                break

        if command_echo_index is not None:
            lines = lines[command_echo_index + 1 :]

        while lines and not lines[0].strip():
            lines.pop(0)

        ### Trim trailing blank lines and shell prompt lines from the output tail.
        while lines and not lines[-1].strip():
            lines.pop()

        ### Remove generic prompt lines from the end of the output.
        while lines and TelnetService._line_matches_prompt(lines[-1], prompt_patterns):
            lines.pop()

        ### Remove trailing echoed command lines such as '<prompt>#show inventory'
        command_candidates = [value.strip() for value in (known_commands or []) if value and value.strip()]
        while lines and TelnetService._line_matches_prompt_with_known_command(lines[-1], command_candidates):
            lines.pop()

        while lines and not lines[-1].strip():
            lines.pop()

        ### Return only the cleaned command body for storage and post-processing.
        return "\n".join(lines).strip()

    @staticmethod
    def _line_matches_prompt_with_known_command(
        line: str,
        known_commands: list[str],
    ) -> bool:
        """Check whether a line ends with an echoed known command after a prompt marker."""
        if not known_commands:
            return False

        normalized_line = ANSI_ESCAPE_RE.sub("", line).replace("\r", "").replace("\x08", "")
        stripped_line = normalized_line.strip()
        if not stripped_line:
            return False

        for known_command in known_commands:
            if re.search(rf"[>#]\s*{re.escape(known_command)}\s*$", stripped_line):
                return True

        return False

    async def _execute_shell_command(
        self,
        reader: Any,
        writer: Any,
        command: str,
        timeout: int,
        wait_for_prompt: bool,
        prompt_patterns: list[re.Pattern[str]],
        pagination_rules: list[PaginationRule],
        known_commands: list[str] | None = None,
    ) -> str:
        """Execute a single command in an interactive Telnet session."""
        ### Drain any stale prompt bytes before issuing the next command
        stale_output = await self._read_trailing_output(reader, idle_timeout=0.02, max_chunks=8)
        if stale_output.strip():
            logger.debug(
                "Discarded %d stale shell byte(s) before command '%s' to avoid output desync",
                len(stale_output),
                command,
            )

        ### Send the command to the Telnet session
        await self._write(writer, f"{command}\n")

        if not wait_for_prompt:
            await asyncio.sleep(0.1)
            return ""

        raw = await self._read_until_patterns(
            reader,
            prompt_patterns,
            timeout,
            writer=writer,
            pagination_rules=pagination_rules,
        )

        ### Return normalized command output
        return self._sanitize_command_output(raw, command, prompt_patterns, known_commands=known_commands)

    @staticmethod
    def _normalize_interactive_input_text(input_text: str) -> str:
        """Normalize common escaped control-sequence forms for interactive input."""
        if input_text in {"\\n", "\\r", "\\r\\n"}:
            return input_text.encode("utf-8").decode("unicode_escape")
        return input_text

    @staticmethod
    def _resolve_interactive_inputs(
        command_def: dict[str, Any],
        enable_password: str | None,
    ) -> list[str]:
        """Resolve interactive input sequence for command steps.

        Supported format:
        - then: ["value1", "value2", ...]
        - Use "{{ enable_password }}" to inject per-device enable password
        """
        ### Check if input is a list
        then_value = command_def.get("then")
        if not isinstance(then_value, list):
            raise RuntimeError(
                "Step failed: 'then' must be a YAML list. "
                "Use 'then: [\"value1\", \"value2\", ...]'"
            )

        raw_inputs: list[str] = []
        for value in then_value:
            ### Nothing configured -> send Enter
            if value is None:
                raw_inputs.append("")
                continue

            ### If placeholder var -> inject enable password (or send Enter if not set)
            text_value = str(value)
            if text_value.strip() == "{{ enable_password }}":
                raw_inputs.append(enable_password or "")
                continue

            raw_inputs.append(text_value)

        if not raw_inputs:
            raise RuntimeError("Step failed: interactive input sequence is empty")

        ### Set max. length of 5 for now
        ## TODO: Don't hardcode this?
        if len(raw_inputs) > 5:
            raise RuntimeError("Step failed: interactive input supports a maximum of 5 entries")

        return [TelnetService._normalize_interactive_input_text(value) for value in raw_inputs]

    async def _run_command_phase(
        self,
        reader: Any,
        writer: Any,
        commands: list[dict[str, Any]],
        default_timeout: int,
        prompt_patterns: list[re.Pattern[str]],
        pagination_rules: list[PaginationRule],
        capture_output: bool,
        enable_password: str | None,
        required: bool = True,
    ) -> list[dict[str, Any]]:
        """Run one command phase and return captured output chunks.

        Supported step modes:
        - command: send `command` and optionally skip wait for prompt
        - command + then: send `command`, then send up to five interactive inputs and optionally skip wait for prompt

        A chunk contains:
        - command: command string
        - output: captured output text
        - metadata: whether this output should be rendered as metadata
        - show_command_in_config: whether command header is embedded before output in config body
        """
        captured_outputs: list[dict[str, Any]] = []
        ### Save commands used in a list
        phase_commands = [
            str(step.get("command") or "").strip()
            for step in commands
            if str(step.get("command") or "").strip()
        ]

        for command_def in commands:
            command = str(command_def.get("command") or "").strip()
            has_then = "then" in command_def

            metadata = bool(command_def.get("metadata", False))
            wait_for_prompt = bool(command_def.get("wait_for_prompt", True))
            show_command_in_config = bool(command_def.get("show_command_in_config", False))

            if metadata and show_command_in_config:
                raise RuntimeError(
                    "Invalid backup command options: 'show_command_in_config: true' "
                    "cannot be used together with 'metadata: true'"
                )

            if has_then and not command:
                raise RuntimeError(
                    "Step failed: 'then' requires a non-empty 'command' in the same step"
                )

            ### Fire interactive input steps (`command` + `then`)
            if has_then:
                try:
                    ### Some devices require a command before interactive input (e.g. 'enable')
                    await self._write(writer, f"{command}\n")
                    await asyncio.sleep(0.1)

                    interactive_inputs = self._resolve_interactive_inputs(command_def, enable_password)

                    ### Send all interactive inputs in sequence, then wait for prompt once
                    for index, input_text in enumerate(interactive_inputs, start=1):
                        if input_text.endswith(("\n", "\r")):
                            await self._write(writer, input_text)
                        else:
                            await self._write(writer, f"{input_text}\n")

                        if index < len(interactive_inputs):
                            await asyncio.sleep(0.1)

                    ### Optionally wait for the prompt after sending input to ensure the device is ready for the next command
                    if wait_for_prompt:
                        await self._read_until_patterns(
                            reader,
                            prompt_patterns,
                            default_timeout,
                            writer=writer,
                            pagination_rules=pagination_rules,
                        )
                    else:
                        await asyncio.sleep(0.1)
                except Exception as ex:
                    if required:
                        raise RuntimeError("Step failed: interactive input") from ex
                    logger.warning("Optional interactive-input step failed: %s", ex)
                continue

            ### Fire command steps
            if not command:
                raise RuntimeError("Step failed: command is empty")

            try:
                output = await self._execute_shell_command(
                    reader=reader,
                    writer=writer,
                    command=command,
                    timeout=default_timeout,
                    wait_for_prompt=wait_for_prompt,
                    prompt_patterns=prompt_patterns,
                    pagination_rules=pagination_rules,
                    known_commands=phase_commands,
                )
                if capture_output and output:
                    captured_outputs.append({
                        "command": command,
                        "output": output,
                        "metadata": metadata,
                        "show_command_in_config": show_command_in_config,
                    })
            except Exception as ex:
                if required:
                    raise RuntimeError(f"Command failed: {command}") from ex
                logger.warning("Optional command failed '%s': %s", command, ex)

        return captured_outputs

    @staticmethod
    def _apply_processing_rules(config: str, rules: dict[str, Any]) -> str:
        """Apply vendor-defined processing pipeline to captured config output.

        Supported processing keys in vendor YAML:
        - strip_patterns: remove matching lines entirely
        - config_start/config_end: crop output to config boundaries
        - redaction.enabled + redaction.patterns: optional secret masking
        """
        ### Get all processing rules for the vendor
        strip_patterns_raw = rules.get("strip_patterns", [])
        start_pattern = rules.get("config_start")
        end_pattern = rules.get("config_end")
        redaction_cfg_raw = rules.get("redaction", {})

        redaction_enabled = isinstance(redaction_cfg_raw, dict) and bool(redaction_cfg_raw.get("enabled", False))
        has_strip_patterns = isinstance(strip_patterns_raw, list) and bool(strip_patterns_raw)
        has_boundaries = bool(start_pattern) or bool(end_pattern)

        ### No processing configured: return config unchanged.
        if not has_strip_patterns and not has_boundaries and not redaction_enabled:
            return config

        ### Replace various line ending types with \n and split into lines for processing
        lines = config.replace("\r\n", "\n").replace("\r", "\n").split("\n")

        ### Step 1: Remove noisy lines before any boundary trimming.
        strip_patterns = strip_patterns_raw
        if isinstance(strip_patterns, list) and strip_patterns:
            compiled_strip: list[re.Pattern[str]] = []
            for pattern in strip_patterns:
                ### Build full strip pattern and skip invalid ones with a warning
                try:
                    compiled_strip.append(re.compile(str(pattern)))
                except re.error as ex:
                    logger.warning("Invalid strip pattern '%s': %s", pattern, ex)

            ### Check every line it matches any of the strip patterns and remove it if it matches
            if compiled_strip:
                lines = [
                    line
                    for line in lines
                    if not any(pattern.search(line) for pattern in compiled_strip)
                ]

        ### Step 2: Crop output based on config_start and config_end patterns
        ## - config_start: first matching line scanning from top
        ## - config_end: first matching line scanning from bottom
        ## If one boundary is missing, we keep from/to the file edge.
        start_index: int | None = None
        end_index: int | None = None

        if start_pattern:
            try:
                start_re = re.compile(str(start_pattern))
                ### Find the first start boundary from the top.
                for index, line in enumerate(lines):
                    if start_re.search(line):
                        start_index = index
                        break
            except re.error as ex:
                ### Invalid boundary regex is ignored, and we continue without start trimming.
                logger.warning("Invalid config_start pattern '%s': %s. Ignoring boundary.", start_pattern, ex)

        if end_pattern:
            try:
                end_re = re.compile(str(end_pattern))
                ### Find the first end boundary from the bottom.
                for index in range(len(lines) - 1, -1, -1):
                    if end_re.search(lines[index]):
                        end_index = index
                        break
            except re.error as ex:
                ### Invalid boundary regex is ignored, and we continue without end trimming.
                logger.warning("Invalid config_end pattern '%s': %s. Ignoring boundary.", end_pattern, ex)

        if lines and (start_index is not None or end_index is not None):
            ### Use full-file defaults when one side is not provided/found.
            start = start_index if start_index is not None else 0
            end = end_index if end_index is not None else len(lines) - 1

            ### Keep the boundary slice only when it is a valid forward range.
            if start <= end:
                lines = lines[start : end + 1]

        processed = "\n".join(lines)

        ### Step 3: Secret redaction; disabled means leave config untouched.
        if isinstance(redaction_cfg_raw, dict) and bool(redaction_cfg_raw.get("enabled", False)):
            redaction_patterns = redaction_cfg_raw.get("patterns", [])
            if isinstance(redaction_patterns, list):
                ### Apply each redaction pattern sequentially to the whole config text
                for redaction_rule in redaction_patterns:
                    if not isinstance(redaction_rule, dict):
                        continue

                    ### Get search regex for this redaction rule.
                    search = redaction_rule.get("search")
                    if not search:
                        continue

                    replacement = str(redaction_rule.get("replacement", "<secret hidden>"))
                    ignore_case = bool(redaction_rule.get("ignore_case", False))
                    flags = re.MULTILINE | (re.IGNORECASE if ignore_case else 0)

                    ### Apply redaction pattern to the whole config text, replacing all matches with the replacement string
                    try:
                        processed = re.sub(str(search), replacement, processed, flags=flags)
                    except re.error as ex:
                        logger.warning("Invalid redaction search '%s': %s", search, ex)

        ### Return the processed config with normalized line endings
        processed = processed.strip("\n")
        return f"{processed}\n"

    async def _login(
        self,
        reader: Any,
        writer: Any,
        username: str,
        password: str,
        prompt_patterns: list[re.Pattern[str]],
        timeout: int,
    ) -> None:
        """Handle basic Telnet login prompts (username/password)."""
        ### Send a 'enter' to the session so the device prints a banner or prompt
        await self._write(writer, "\n")
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
                await self._write(writer, f"{username}\n")
                sent_username = True
                buffer = ""
                inactivity_deadline = loop.time() + timeout_seconds
                continue

            ### Send password on password prompts
            if tail_lines and not sent_password and self._line_matches_any(tail_lines[-1], LOGIN_PASSWORD_PATTERNS):
                await self._write(writer, f"{password}\n")
                sent_password = True
                buffer = ""
                inactivity_deadline = loop.time() + timeout_seconds
                continue

            remaining = inactivity_deadline - loop.time()
            if remaining <= 0:
                raise asyncio.TimeoutError("Timed out waiting for Telnet login prompt")

            try:
                chunk = await asyncio.wait_for(
                    reader.read(READ_CHUNK_SIZE),
                    timeout=min(remaining, READ_POLL_INTERVAL_SECONDS),
                )
            except asyncio.TimeoutError:
                continue

            if chunk == "":
                return

            buffer += chunk
            inactivity_deadline = loop.time() + timeout_seconds

    async def _collect_vendor_config(
        self,
        reader: Any,
        writer: Any,
        vendor_id: str,
        default_timeout: int,
        enable_password: str | None,
    ) -> tuple[str, str | None]:
        """Collect configuration and metadata from device via vendor-defined command phases."""
        ### Get command sets for the vendor (pre_backup, backup, post_backup)
        command_sets = vendor_service.get_backup_commands(vendor_id, protocol="telnet")
        backup_commands = command_sets.get("backup")
        if not backup_commands:
            raise ValueError(f"Vendor '{vendor_id}' has no backup commands configured")

        ### Get session parameters for the vendor
        session_config = vendor_service.get_session_parameters(vendor_id)
        prefix = str(session_config.get("comment_prefix", "! ")).strip()
        comment_prefix = "! " if not prefix else (prefix if prefix.endswith(" ") else f"{prefix} ")
        include_metadata_in_config = bool(session_config.get("include_metadata_in_config", False))
        prompt_patterns = self._get_prompt_patterns(vendor_id)
        pagination_rules = self._get_pagination_settings(vendor_id)

        ### Get processing rules for the vendor
        processing_rules = vendor_service.get_processing_rules(vendor_id)

        ### Run command phases in interactive shell session and capture output
        pre_backup_commands = command_sets.get("pre_backup", [])
        post_backup_commands = command_sets.get("post_backup", [])

        captured_output: list[dict[str, Any]] = []
        try:
            ### Write an initial newline to ensure we get a prompt before starting commands
            await self._write(writer, "\n")

            ### Wait for the initial prompt to ensure the shell is ready before sending commands
            try:
                await self._read_until_patterns(reader, prompt_patterns, default_timeout)
            except asyncio.TimeoutError:
                logger.debug(
                    "Initial prompt wait timed out for vendor '%s'; retrying once after additional newline",
                    vendor_id,
                )
                await self._write(writer, "\n")
                await self._read_until_patterns(reader, prompt_patterns, default_timeout)

            ### Run commands
            ## pre_backup
            await self._run_command_phase(
                reader=reader,
                writer=writer,
                commands=pre_backup_commands,
                default_timeout=default_timeout,
                prompt_patterns=prompt_patterns,
                pagination_rules=pagination_rules,
                capture_output=False,
                enable_password=enable_password,
            )

            ## backup
            captured_output = await self._run_command_phase(
                reader=reader,
                writer=writer,
                commands=backup_commands,
                default_timeout=default_timeout,
                prompt_patterns=prompt_patterns,
                pagination_rules=pagination_rules,
                capture_output=True,
                enable_password=None,
            )

            ## post_backup
            await self._run_command_phase(
                reader=reader,
                writer=writer,
                commands=post_backup_commands,
                default_timeout=default_timeout,
                prompt_patterns=prompt_patterns,
                pagination_rules=pagination_rules,
                capture_output=False,
                enable_password=None,
                required=False, # Set to false so backup capture can still succeed even if post_backup fails
            )
        finally:
            ### Attempt graceful close if the writer supports it
            close = getattr(writer, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

            if writer is not None:
                ### Wait for the connection to fully close before the next retry attempt to avoid overlapping sessions
                ### Use a short grace period and skip if the close future is on a different loop
                await self._safe_wait_closed(writer, timeout=1.5)

        non_metadata_outputs: list[str] = []
        for chunk in captured_output:
            if bool(chunk.get("metadata", False)):
                continue

            output = str(chunk.get("output", "")).strip()
            if not output:
                continue

            if bool(chunk.get("show_command_in_config", False)):
                command = str(chunk.get("command", "")).strip()
                if command:
                    output = f"{comment_prefix}Command used: {command}\n{output}"

            non_metadata_outputs.append(output)

        ### Fill raw_config with non_metadata_outputs while preserving their order and seperating the chunks with 2 newlines
        raw_config = "\n\n".join(output for output in non_metadata_outputs if output)
        if not raw_config:
            raise RuntimeError("Backup commands completed but returned empty non-metadata config output")

        ### Apply vendor-defined processing rules
        processed_config = self._apply_processing_rules(raw_config, processing_rules)

        ### Build metadata section from captured output marked as metadata=true
        metadata_section = self._build_metadata_section(captured_output, comment_prefix)

        metadata_output = metadata_section if metadata_section else None

        if include_metadata_in_config and metadata_section and processed_config:
            return f"{metadata_section}\n\n{processed_config}", metadata_output
        return processed_config, metadata_output

    async def _collect_local_vendor_config(
        self,
        device: DeviceBase,
        vendor_id: str,
        timeout_seconds: int,
    ) -> tuple[str, str | None]:
        """Collect config in local test mode while reusing vendor processing rules."""
        ### Keep vendor command validation parity with real Telnet path.
        command_sets = vendor_service.get_backup_commands(vendor_id, protocol="telnet")
        backup_commands = command_sets.get("backup")
        if not backup_commands:
            raise ValueError(f"Vendor '{vendor_id}' has no backup commands configured")

        raw_config = await asyncio.wait_for(
            local_ssh_simulator.get_config(device),
            timeout=timeout_seconds,
        )
        if not raw_config.strip():
            raise RuntimeError("Local simulator returned empty config output")

        processing_rules = vendor_service.get_processing_rules(vendor_id)
        return self._apply_processing_rules(raw_config, processing_rules), None

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

        max_attempts = retry_count + 1

        ### Use the local simulator if test mode is enabled
        if self.settings.local_test_mode:
            return await self._collect_local_vendor_config(
                device=device,
                vendor_id=vendor_id,
                timeout_seconds=timeout_seconds,
            )

        ### Try to fetch config from device with commands defined in vendor YAML, apply retries on failure
        last_exception: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            reader: Any | None = None
            writer: Any | None = None
            try:
                loop = asyncio.get_running_loop()
                asyncio.set_event_loop(loop)
                connect_kwargs = self._build_open_connection_kwargs(
                    host=str(device.ip_address),
                    port=device_port,
                    timeout=timeout_seconds,
                    loop=loop,
                )
                
                ### Connect via Telnet using
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

                prompt_patterns = self._get_prompt_patterns(vendor_id)
                await self._login(
                    reader=reader,
                    writer=writer,
                    username=device_username,
                    password=device_password,
                    prompt_patterns=prompt_patterns,
                    timeout=timeout_seconds,
                )

                ### Fun part: Run the configured command phases to capture device config
                config, metadata_output = await self._collect_vendor_config(
                    reader=reader,
                    writer=writer,
                    vendor_id=vendor_id,
                    default_timeout=timeout_seconds,
                    enable_password=enable_password,
                )
                if attempt > 1:
                    logger.warning(
                        "Config fetch for device '%s' succeeded on retry attempt %d/%d",
                        device.device_name,
                        attempt,
                        max_attempts,
                    )
                return config, metadata_output
            except asyncio.TimeoutError as ex:
                ### Log timeout error if Telnet connection times out or if waiting for command output exceeds timeout
                last_exception = TimeoutError(
                    f"Telnet config fetch timed out after {timeout_seconds}s "
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
                if writer is not None:
                    try:
                        ### Attempt graceful close if the writer supports it
                        close = getattr(writer, "close", None)
                        if callable(close):
                            close()
                    except Exception:
                        pass

                    ### Wait for the connection to fully close before the next retry attempt to avoid overlapping sessions
                    ### Use a short grace period and skip if the close future is on a different loop
                    await self._safe_wait_closed(writer, timeout=1.5)

            if attempt < max_attempts:
                await asyncio.sleep(0.25)

        if last_exception is not None:
            raise last_exception
        raise RuntimeError("Telnet config fetch failed without a captured exception!!")


### Singleton instance
telnet_service = TelnetService()
