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
GENERIC_PROMPT_RE = re.compile(r"[^\r\n=]*[A-Za-z0-9][^\r\n=]*[>#]\s*$")

GENERIC_PROMPT_PATTERNS = [GENERIC_PROMPT_RE]


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
        normalized_line = ANSI_ESCAPE_RE.sub("", line).replace("\r", "")
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
            return compiled_patterns

        logger.warning(
            "No valid session.prompt patterns for vendor '%s'; using generic prompt pattern",
            vendor_id,
        )
        return GENERIC_PROMPT_PATTERNS

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
    ) -> str:
        """Read stream until one of the patterns appears or timeout is reached."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(1, int(timeout))
        buffer = ""

        ### Read in a loop until we see a prompt pattern or hit the timeout
        while True:
            ### Check if any prompt pattern matches the current output line
            ## Evaluating only the last line avoids false positives from earlier content..
            ## ..and from random chunk boundaries inside large command outputs
            if patterns:
                tail = buffer[-4096:]
                last_line = tail.split("\n")[-1]
                if self._line_matches_prompt(last_line, patterns):
                    ### Collect any trailing bytes that arrive immediately after prompt detection
                    ### This reduces output bleed into the next command on some devices
                    buffer += await self._read_trailing_output(stream)
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
    ) -> str:
        """Execute a single command in an interactive shell session."""
        ### Send the command to the shell
        process.stdin.write(f"{command}\n")

        if not wait_for_prompt:
            await asyncio.sleep(0.1)
            return ""

        ### Wait until shell responds with a prompt again (shell is ready again)
        raw = await self._read_until_patterns(process.stdout, prompt_patterns, timeout)

        ### Return normalized command output
        return self._sanitize_command_output(raw, command, prompt_patterns)

    async def _run_command_phase(
        self,
        process: asyncssh.SSHClientProcess,
        commands: list[dict[str, Any]],
        default_timeout: int,
        password: str,
        prompt_patterns: list[re.Pattern[str]],
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
        - metadata: whether this output should be rendered as metadata
        - show_command_in_config: whether command header is embedded before output in config body
        """
        captured_outputs: list[dict[str, Any]] = []

        for command_def in commands:
            ### Get type of the step
            step_type = str(command_def.get("type") or "command")
            step_type = step_type.strip().lower()

            metadata = bool(command_def.get("metadata", False))
            wait_for_prompt = bool(command_def.get("wait_for_prompt", True))
            show_command_in_config = bool(command_def.get("show_command_in_config", False))

            if metadata and show_command_in_config:
                raise RuntimeError(
                    "Invalid backup command options: 'show_command_in_config: true' "
                    "cannot be used together with 'metadata: true'"
                )

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
                            prompt_patterns,
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
                    prompt_patterns=prompt_patterns,
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
        password: str | None,
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

        ### Get processing rules for the vendor
        processing_rules = vendor_service.get_processing_rules(vendor_id)

        ### Run command phases in interactive shell session and capture output
        async with connection.create_process(term_type="vt100", encoding="utf-8") as process:
            ### Write an initial newline to ensure we get a prompt before starting commands
            process.stdin.write("\n")

            ### Wait for the initial prompt to ensure the shell is ready before sending commands
            await self._read_until_patterns(process.stdout, prompt_patterns, default_timeout)

            ### Run pre_backup commands (required for session setup consistency)
            await self._run_command_phase(
                process=process,
                commands=command_sets.get("pre_backup", []),
                default_timeout=default_timeout,
                password=password,
                prompt_patterns=prompt_patterns,
                capture_output=False,
            )

            captured_output = await self._run_command_phase(
                process=process,
                commands=backup_commands,
                default_timeout=default_timeout,
                password=password,
                prompt_patterns=prompt_patterns,
                capture_output=True,
            )

            await self._run_command_phase(
                process=process,
                commands=command_sets.get("post_backup", []),
                default_timeout=default_timeout,
                password=password,
                prompt_patterns=prompt_patterns,
                capture_output=False,
            )

            ### Exit shell
            process.stdin.write("exit\n")

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
        ssh_profile = str(device_config["ssh_profile"]).strip()
        device_username = str(device_config["username"]).strip()

        ### Device authentication can be password-based, key-based, or both.
        device_password_raw = str(device_config.get("password") or "").strip()
        device_password = device_password_raw if device_password_raw else None
        device_key_file_raw = str(device_config.get("ssh_key_file") or "").strip()
        device_ssh_key_file = device_key_file_raw if device_key_file_raw else None

        ### Jump-host settings are optional and already validated in get_device_config
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
                        ssh_profile=ssh_profile,
                        timeout=timeout_seconds,
                        connection_label=f"jumphost:{jumphost_name}",
                    )

                ### Connect via SSH using SSH profile options
                connection = await self.connect(
                    host=str(device.ip_address),
                    username=device_username,
                    password=device_password,
                    ssh_key_file=device_ssh_key_file,
                    ssh_profile=ssh_profile,
                    timeout=timeout_seconds,
                    tunnel=jump_connection,
                    connection_label=device.device_name,
                )

                ### Fun part: Run the configured command phases to capture device config
                config, metadata_output = await self._collect_vendor_config(
                    connection=connection,
                    vendor_id=vendor_id,
                    default_timeout=timeout_seconds,
                    password=device_password,
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
