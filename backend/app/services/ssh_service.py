"""SSH connection service using asyncssh."""

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

import asyncssh

from app.core import get_settings
from app.models.device import DeviceBase
from app.services.vendor_service import vendor_service
from app.services.local_ssh_simulator import local_ssh_simulator

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
        re.compile(r"[^\r\n=]*[A-Za-z0-9][^\r\n=]*[>#]\s*$"),
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

PaginationRule = tuple[re.Pattern[str], str]


class SSHService:
    """Service for SSH connections to network devices."""

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
            return [(pattern, " ") for pattern in DEFAULT_PAGINATION_PATTERNS]

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
        stream: asyncssh.SSHReader,
        patterns: list[re.Pattern[str]],
        timeout: int,
        *,
        stdin: Any | None = None,
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
                    ### Collect any trailing bytes that arrive immediately after prompt detection
                    ### This reduces output bleed into the next command on some devices
                    buffer += await self._read_trailing_output(stream)
                    return buffer

                ### Handle pagination prompts by sending the response for the matching pagination rule
                matched_pagination_response = None
                if tail_lines and resolved_pagination_rules:
                    matched_pagination_response = self._match_pagination_response(
                        tail_lines[-1],
                        resolved_pagination_rules,
                    )

                if matched_pagination_response is not None:
                    if stdin is not None:
                        stdin.write(matched_pagination_response)

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
                chunk = await asyncio.wait_for(stream.read(256), timeout=min(remaining, 1.0))
            except asyncio.TimeoutError:
                ### No new bytes in this polling window; keep waiting until overall deadline
                continue

            if chunk == "":
                return buffer

            ### Append the new chunk to the buffer and continue checking for patterns
            buffer += chunk

            ### Timeout tracks inactivity, not total command runtime
            inactivity_deadline = loop.time() + timeout_seconds

    @staticmethod
    async def _read_trailing_output(
        stream: asyncssh.SSHReader,
        idle_timeout: float = 0.05,
        max_chunks: int = 16,
    ) -> str:
        """Read immediately available trailing output after prompt detection."""
        trailing = ""
        for _ in range(max_chunks):
            try:
                chunk = await asyncio.wait_for(stream.read(256), timeout=idle_timeout)
            except asyncio.TimeoutError:
                break

            if chunk == "":
                break

            trailing += chunk

        return trailing

    @staticmethod
    def _sanitize_command_output(
        raw_output: str,
        command: str,
        prompt_patterns: list[re.Pattern[str]],
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
        while lines and SSHService._line_matches_prompt(lines[-1], prompt_patterns):
            lines.pop()

        ### Return only the cleaned command body for storage and post-processing.
        return "\n".join(lines).strip()

    async def _execute_shell_command(
        self,
        process: asyncssh.SSHClientProcess,
        command: str,
        timeout: int,
        wait_for_prompt: bool,
        prompt_patterns: list[re.Pattern[str]],
        pagination_rules: list[PaginationRule],
    ) -> str:
        """Execute a single command in an interactive shell session."""
        ### Send the command to the shell
        process.stdin.write(f"{command}\n")

        if not wait_for_prompt:
            await asyncio.sleep(0.1)
            return ""

        ### Wait until shell responds with a prompt again (shell is ready again)
        raw = await self._read_until_patterns(
            process.stdout,
            prompt_patterns,
            timeout,
            stdin=process.stdin,
            pagination_rules=pagination_rules,
        )

        ### Return normalized command output
        return self._sanitize_command_output(raw, command, prompt_patterns)

    @staticmethod
    def _normalize_interactive_input_text(input_text: str) -> str:
        """Normalize common escaped control-sequence forms for interactive input."""
        if input_text in {"\\n", "\\r", "\\r\\n"}:
            return input_text.encode("utf-8").decode("unicode_escape")
        return input_text

    @staticmethod
    def _resolve_interactive_inputs(command_def: dict[str, Any]) -> list[str]:
        """Resolve interactive input sequence for command steps.

        Supported format:
        - then: ["value1", "value2", ...]
        """
        ### Check if input is a list
        then_value = command_def.get("then")
        if not isinstance(then_value, list):
            raise RuntimeError(
                "Step failed: 'then' must be a YAML list. "
                "Use 'then: [\"value1\", \"value2\", ...]'"
            )

        raw_inputs = ["" if value is None else str(value) for value in then_value]

        if not raw_inputs:
            raise RuntimeError("Step failed: interactive input sequence is empty")

        ### Set max. length of 5 for now
        ## TODO: Don't hardcode this?
        if len(raw_inputs) > 5:
            raise RuntimeError("Step failed: interactive input supports a maximum of 5 entries")

        return [SSHService._normalize_interactive_input_text(value) for value in raw_inputs]

    async def _run_command_phase(
        self,
        process: asyncssh.SSHClientProcess,
        commands: list[dict[str, Any]],
        default_timeout: int,
        prompt_patterns: list[re.Pattern[str]],
        pagination_rules: list[PaginationRule],
        capture_output: bool,
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

            ### Fire interactive input steps (`command` + `then`)
            if has_then:
                try:
                    ### Some devices require a command before interactive input (e.g. 'enable')
                    if command:
                        process.stdin.write(f"{command}\n")
                        await asyncio.sleep(0.1)

                    interactive_inputs = self._resolve_interactive_inputs(command_def)

                    ### Send all interactive inputs in sequence, then wait for prompt once
                    for index, input_text in enumerate(interactive_inputs, start=1):
                        if input_text.endswith(("\n", "\r")):
                            process.stdin.write(input_text)
                        else:
                            process.stdin.write(f"{input_text}\n")

                        if index < len(interactive_inputs):
                            await asyncio.sleep(0.1)

                    ### Optionally wait for the prompt after sending input to ensure the device is ready for the next command
                    if wait_for_prompt:
                        await self._read_until_patterns(
                            process.stdout,
                            prompt_patterns,
                            default_timeout,
                            stdin=process.stdin,
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
                    process=process,
                    command=command,
                    timeout=default_timeout,
                    wait_for_prompt=wait_for_prompt,
                    prompt_patterns=prompt_patterns,
                    pagination_rules=pagination_rules,
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

    async def _collect_vendor_config(
        self,
        connection: asyncssh.SSHClientConnection,
        vendor_id: str,
        default_timeout: int,
    ) -> tuple[str, str | None]:
        """Collect configuration and metadata from device via vendor-defined command phases."""
        ### Get command sets for the vendor (pre_backup, backup, post_backup)
        command_sets = vendor_service.get_backup_commands(vendor_id)
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

        process = await connection.create_process(term_type="vt100", encoding="utf-8")
        captured_output: list[dict[str, Any]] = []
        try:
            ### Write an initial newline to ensure we get a prompt before starting commands
            process.stdin.write("\n")

            ### Wait for the initial prompt to ensure the shell is ready before sending commands
            await self._read_until_patterns(process.stdout, prompt_patterns, default_timeout)

            ### Run pre_backup commands (required for session setup consistency)
            await self._run_command_phase(
                process=process,
                commands=pre_backup_commands,
                default_timeout=default_timeout,
                password=password,
                prompt_patterns=prompt_patterns,
                pagination_rules=pagination_rules,
                capture_output=False,
            )

            captured_output = await self._run_command_phase(
                process=process,
                commands=backup_commands,
                default_timeout=default_timeout,
                password=password,
                prompt_patterns=prompt_patterns,
                pagination_rules=pagination_rules,
                capture_output=True,
            )

            await self._run_command_phase(
                process=process,
                commands=post_backup_commands,
                default_timeout=default_timeout,
                password=password,
                prompt_patterns=prompt_patterns,
                pagination_rules=pagination_rules,
                capture_output=False,
            )

        finally:
            ### Always force-close local shell handle; if already closed this isn't needed
            forced_close_wait_timeout_seconds = 1.5
            try:
                close = getattr(process, "close", None)
                if callable(close):
                    close()
                else:
                    channel = getattr(process, "channel", None)
                    if channel is None and hasattr(process, "stdin"):
                        channel = getattr(process.stdin, "channel", None)
                    if channel is not None:
                        channel.close()
            except Exception as ex:
                logger.debug(
                    "Forced shell close failed for vendor '%s' (%s: %s); continuing outer SSH connection cleanup",
                    vendor_id,
                    ex.__class__.__name__,
                    ex,
                )

            wait_closed = getattr(process, "wait_closed", None)
            if callable(wait_closed):
                try:
                    await asyncio.wait_for(wait_closed(), timeout=forced_close_wait_timeout_seconds)
                except Exception:
                    pass

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
        ### Keep vendor command validation parity with real SSH path.
        command_sets = vendor_service.get_backup_commands(vendor_id)
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
    ) -> tuple[str, str | None]:
        """Get device configuration plus optional metadata via local simulator or real SSH."""
        ### Get device config
        device_config = self.settings.get_device_config(device.group, device.device_name)

        ### Filter for required SSH config values
        timeout_seconds = int(device_config["timeout"])
        retry_count = int(device_config["retry"])
        vendor_id = str(device_config["vendor"]).strip()
        device_ssh_profile = str(device_config["ssh_profile"]).strip()
        device_ssh_port = int(device_config.get("ssh_port") or 22)
        device_username = str(device_config["username"]).strip()

        ### Device authentication can be password-based, key-based, or both.
        device_password_raw = str(device_config.get("password") or "").strip()
        device_password = device_password_raw if device_password_raw else None
        device_key_file_raw = str(device_config.get("ssh_key_file") or "").strip()
        device_ssh_key_file = device_key_file_raw if device_key_file_raw else None

        ### Jumphost settings are optional and already validated in get_device_config
        jumphost_cfg = device_config.get("jumphost")
        
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
                    port=device_ssh_port,
                    ssh_profile=device_ssh_profile,
                    timeout=timeout_seconds,
                    tunnel=jump_connection,
                    connection_label=device.device_name,
                )

                ### Fun part: Run the configured command phases to capture device config
                config, metadata_output = await self._collect_vendor_config(
                    connection=connection,
                    vendor_id=vendor_id,
                    default_timeout=timeout_seconds,
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

                ### Always close jumphost tunnel after device connection closes
                if jump_connection is not None:
                    jump_connection.close()
                    try:
                        await jump_connection.wait_closed()
                    except Exception:
                        pass

            if attempt < max_attempts:
                await asyncio.sleep(0.25)

        if last_exception is not None:
            raise last_exception
        raise RuntimeError("SSH config fetch failed without a captured exception!!")


### Singleton instance
ssh_service = SSHService()
