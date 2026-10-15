"""Protocol-independent helpers shared by the SSH, Telnet and HTTP(S) backup services."""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from app.models.device import DeviceBase

logger = logging.getLogger(__name__)


def apply_processing_rules(config: str, rules: dict[str, Any]) -> str:
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


async def fetch_with_retries(
    device: DeviceBase,
    fetch_once: Callable[[], Awaitable[tuple[str, str | None]]],
    *,
    max_attempts: int,
    timeout_seconds: int,
    protocol_label: str,
    timeout_exceptions: tuple[type[BaseException], ...] = (asyncio.TimeoutError,),
) -> tuple[str, str | None]:
    """Run one config fetch attempt up to max_attempts times and return the first success.

    fetch_once must open and close its own connection, so a failed attempt never leaks into the next one.
    """
    last_exception: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            config, metadata_output = await fetch_once()
            if attempt > 1:
                logger.warning(
                    "Config fetch for device '%s' succeeded on retry attempt %d/%d",
                    device.device_name,
                    attempt,
                    max_attempts,
                )
            return config, metadata_output
        except timeout_exceptions as ex:
            ### Log timeout error if the connection times out or if waiting for output exceeds timeout
            last_exception = TimeoutError(
                f"{protocol_label} config fetch timed out after {timeout_seconds}s "
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

        ### Wait 0.25sec and try again if there are remaining attempts
        if attempt < max_attempts:
            await asyncio.sleep(0.25)

    if last_exception is not None:
        raise last_exception
    raise RuntimeError(f"{protocol_label} config fetch failed without a captured exception!!")
