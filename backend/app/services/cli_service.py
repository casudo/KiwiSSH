"""Shared interactive CLI handling for the SSH and Telnet backup services.

Both protocols drive the same kind of interactive shell: wait for a prompt, send vendor commands,
answer pagination prompts and clean up the captured output. Only opening the connection, logging in
and how bytes are read and written differ, which is what CLISession and the subclass hooks cover.
"""

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

from app.core import Settings, get_settings
from app.models.device import DeviceBase
from app.services.local_ssh_simulator import local_ssh_simulator
from app.services.protocol_common import apply_processing_rules
from app.services.vendor_service import vendor_service

logger = logging.getLogger(__name__)

ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

### Generic prompt detection used for all vendors as default
## Matches common prompt shapes like:
## - hostname#
## - hostname>
## - hostname(config)#
## - [user@host ~]#
## Notes:
## - Excludes '=' to avoid matching config assignment lines
GENERIC_PROMPT_PATTERNS = [
        re.compile(r"(?=[^\r\n=]*[A-Za-z0-9])[^\r\n=]*[>#]\s*$"),
    ]

### Generic pagination patterns to handle common pagination for all vendors as default
DEFAULT_PAGINATION_PATTERNS = [
    re.compile(r"^\s*--\s*More\s*--\s*(?:\(\d+%\))?\s*$", re.IGNORECASE),
    re.compile(r"^\s*---\s*\(more(?: \d+%)?\)\s*---\s*$", re.IGNORECASE),
    re.compile(r"^\s*More:\s*<space>,\s*Quit:\s*q,\s*One line:\s*<return>\s*$", re.IGNORECASE),
    re.compile(r"^\s*Press any key to continue(?: or q to quit)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*Press <space> to continue(?:, q to quit)?\s*$", re.IGNORECASE),
]
DEFAULT_PAGINATION_RESPONSE = " "
READ_CHUNK_SIZE = 4096
READ_POLL_INTERVAL_SECONDS = 1.0
LARGE_OUTPUT_TIMEOUT_THRESHOLD_BYTES = 256 * 1024
LARGE_OUTPUT_INACTIVITY_TIMEOUT_SECONDS = 90
PROMPT_CONFIRM_IDLE_SECONDS = 0.2
PROMPT_CONFIRM_MAX_SECONDS = 2.0

PaginationRule = tuple[re.Pattern[str], str]


class CLISession(ABC):
    """An open interactive shell on a device, independent of the protocol carrying it."""

    @abstractmethod
    async def read(self, size: int) -> str:
        """Read up to size characters; returns "" once the session is closed."""

    @abstractmethod
    async def write(self, data: str) -> None:
        """Send data to the shell."""

    @abstractmethod
    async def close(self) -> None:
        """Close the shell; must be safe to call more than once."""


class CLIService(ABC):
    """Base class for backup services that capture config through an interactive CLI shell."""

    ### Protocol key used to look up vendor commands (e.g. 'ssh' or 'telnet')
    PROTOCOL: str
    ### Human readable protocol name for messages (e.g. 'SSH' or 'Telnet')
    PROTOCOL_LABEL: str

    @property
    def settings(self) -> Settings:
        """Current settings, resolved on every access so a settings reload never leaves a stale copy behind."""
        return get_settings()

    ### =============================================================================
    ### Prompt and Pagination Detection
    ### =============================================================================

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

    ### =============================================================================
    ### Reading Shell Output
    ### =============================================================================

    async def _read_until_patterns(
        self,
        session: CLISession,
        patterns: list[re.Pattern[str]],
        timeout: int,
        *,
        pagination_rules: list[PaginationRule] | None = None,
    ) -> str:
        """Read the session until one of the patterns appears or timeout is reached."""
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
                        ### Allow a longer quiet window to catch late chunks from large outputs
                        idle_timeout = max(idle_timeout, 0.4)
                        max_total_seconds = max(max_total_seconds, 4.0)
                    trailing = await self._read_trailing_output(
                        session,
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
                    await session.write(matched_pagination_response)

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
                    session.read(READ_CHUNK_SIZE),
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
        session: CLISession,
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
                chunk = await asyncio.wait_for(session.read(READ_CHUNK_SIZE), timeout=idle_timeout)
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
        while lines and CLIService._line_matches_prompt(lines[-1], prompt_patterns):
            lines.pop()

        ### Remove trailing echoed command lines such as '<prompt>#show inventory'
        command_candidates = [value.strip() for value in (known_commands or []) if value and value.strip()]
        while lines and CLIService._line_matches_prompt_with_known_command(lines[-1], command_candidates):
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

    ### =============================================================================
    ### Running Commands
    ### =============================================================================

    async def _execute_shell_command(
        self,
        session: CLISession,
        command: str,
        timeout: int,
        wait_for_prompt: bool,
        prompt_patterns: list[re.Pattern[str]],
        pagination_rules: list[PaginationRule],
        known_commands: list[str] | None = None,
    ) -> str:
        """Execute a single command in an interactive shell session."""
        ### Drain any stale prompt bytes before issuing the next command
        stale_output = await self._read_trailing_output(session, idle_timeout=0.02, max_chunks=8)
        if stale_output.strip():
            logger.debug(
                "Discarded %d stale shell byte(s) before command '%s' to avoid output desync",
                len(stale_output),
                command,
            )

        ### Send the command to the shell
        await session.write(f"{command}\n")

        if not wait_for_prompt:
            await asyncio.sleep(0.1)
            return ""

        ### Wait until shell responds with a prompt again (shell is ready again)
        raw = await self._read_until_patterns(
            session,
            prompt_patterns,
            timeout,
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

        return [CLIService._normalize_interactive_input_text(value) for value in raw_inputs]

    async def _run_command_phase(
        self,
        session: CLISession,
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
                    await session.write(f"{command}\n")
                    await asyncio.sleep(0.1)

                    interactive_inputs = self._resolve_interactive_inputs(command_def, enable_password)

                    ### Send all interactive inputs in sequence, then wait for prompt once
                    for index, input_text in enumerate(interactive_inputs, start=1):
                        if input_text.endswith(("\n", "\r")):
                            await session.write(input_text)
                        else:
                            await session.write(f"{input_text}\n")

                        if index < len(interactive_inputs):
                            await asyncio.sleep(0.1)

                    ### Optionally wait for the prompt after sending input to ensure the device is ready for the next command
                    if wait_for_prompt:
                        await self._read_until_patterns(
                            session,
                            prompt_patterns,
                            default_timeout,
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
                    session=session,
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

    ### =============================================================================
    ### Collecting the Config
    ### =============================================================================

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
        """Protocol-specific steps after the shell opened and before the first prompt is awaited (e.g. login)."""

    async def _collect_vendor_config(
        self,
        session: CLISession,
        vendor_id: str,
        default_timeout: int,
        enable_password: str | None,
        *,
        username: str,
        password: str | None,
    ) -> tuple[str, str | None]:
        """Collect configuration and metadata from device via vendor-defined command phases.

        The session is always closed when this returns or raises.
        """
        try:
            ### Get command sets for the vendor (pre_backup, backup, post_backup)
            command_sets = vendor_service.get_backup_commands(vendor_id, protocol=self.PROTOCOL)
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

            ### Protocol-specific steps such as logging in
            await self._prepare_session(
                session,
                vendor_id,
                session_config,
                prompt_patterns,
                username=username,
                password=password,
                timeout=default_timeout,
            )

            ### Write an initial newline to ensure we get a prompt before starting commands
            await session.write("\n")

            ### Wait for the initial prompt to ensure the shell is ready before sending commands
            try:
                await self._read_until_patterns(session, prompt_patterns, default_timeout)
            except asyncio.TimeoutError:
                logger.debug(
                    "Initial prompt wait timed out for vendor '%s'; retrying once after additional newline",
                    vendor_id,
                )
                await session.write("\n")
                await self._read_until_patterns(session, prompt_patterns, default_timeout)

            ### Run commands
            ## pre_backup
            await self._run_command_phase(
                session=session,
                commands=pre_backup_commands,
                default_timeout=default_timeout,
                prompt_patterns=prompt_patterns,
                pagination_rules=pagination_rules,
                capture_output=False,
                enable_password=enable_password,
            )

            ## backup
            captured_output = await self._run_command_phase(
                session=session,
                commands=backup_commands,
                default_timeout=default_timeout,
                prompt_patterns=prompt_patterns,
                pagination_rules=pagination_rules,
                capture_output=True,
                enable_password=None,
            )

            ## post_backup
            await self._run_command_phase(
                session=session,
                commands=post_backup_commands,
                default_timeout=default_timeout,
                prompt_patterns=prompt_patterns,
                pagination_rules=pagination_rules,
                capture_output=False,
                enable_password=None,
                required=False, # Set to false so backup capture can still succeed even if post_backup fails
            )
        finally:
            ### Always close the shell, also so the next retry attempt never overlaps with this session
            await session.close()

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
        processed_config = apply_processing_rules(raw_config, processing_rules)

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
        ### Keep vendor command validation parity with the real protocol path
        command_sets = vendor_service.get_backup_commands(vendor_id, protocol=self.PROTOCOL)
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
        return apply_processing_rules(raw_config, processing_rules), None

    @abstractmethod
    async def get_config(
        self,
        device: DeviceBase,
        *,
        device_config: dict[str, Any] | None = None,
    ) -> tuple[str, str | None]:
        """Get device configuration plus optional metadata."""
