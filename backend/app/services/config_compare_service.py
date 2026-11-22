"""Compare the configurations of two devices."""

import asyncio
import ipaddress
import logging
import re
import tempfile
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from git import Git

from app.core import get_settings
from app.models.backup import BuiltinIgnoreRule
from app.services.protocol_common import apply_processing_rules

logger = logging.getLogger(__name__)

### Text matching a custom ignore pattern is replaced with this in both configs before they're compared
IGNORED_TEXT_PLACEHOLDER = "<ignored>"
MAX_IGNORE_PATTERNS = 50
MAX_IGNORE_PATTERN_LENGTH = 500

### Text matching a built-in ignore rule is replaced with these placeholder str
BUILTIN_PLACEHOLDERS: dict[BuiltinIgnoreRule, str] = {
    BuiltinIgnoreRule.HOSTNAME: "<hostname>",
    BuiltinIgnoreRule.IPV4: "<ipv4>",
    BuiltinIgnoreRule.IPV6: "<ipv6>",
    BuiltinIgnoreRule.MAC: "<mac>",
}

### Shorter hostnames arent masked
MIN_MASKED_DEVICE_NAME_LENGTH = 3

### Value of common hostname statements: hostname (Cisco, Arista, ProCurve, ...), set hostname (FortiOS), host-name (Junos),..
## ..sysname (Huawei, Comware), switchname (NX-OS) and configure snmp sysName (EXOS)
_HOSTNAME_STATEMENT = re.compile(
    r"^([ \t]*(?:set[ \t]+|configure[ \t]+snmp[ \t]+)?(?:system[ \t]+)?(?:hostname|host-name|sysname|switchname)"
    r"(?:[ \t]*[=:][ \t]*|[ \t]+))"
    r"(\"[^\"\n]*\"|'[^'\n]*'|[^\s;]+)",
    re.IGNORECASE | re.MULTILINE,
)
_IPV4 = re.compile(r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?!\.?\d)")
### Only a candidate, it also matches times (12:30:45) or MAC addresses, so every match is validated with the ipaddress module
_IPV6_CANDIDATE = re.compile(r"(?<![\w:.])(?:[0-9A-Fa-f]{0,4}:){2,7}(?:\d{1,3}(?:\.\d{1,3}){3}|[0-9A-Fa-f]{0,4})(?![\w:.])")
_MAC = re.compile(
    r"(?<![\w:.-])(?:"
    r"[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}"  # 00:11:22:33:44:55 or 00-11-22-33-44-55
    r"|[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}"  # 0011.2233.4455 (Cisco)
    r"|[0-9A-Fa-f]{6}-[0-9A-Fa-f]{6}"  # 001122-334455 (ProCurve)
    r")(?![\w:.-])"
)


def _mask_ipv4(match: re.Match[str]) -> str:
    """Mask an IPv4 address, but keep netmasks and wildcard masks (e.g. 255.255.255.0, 0.0.0.255) visible."""
    text = match.group()
    try:
        ipaddress.IPv4Network(f"0.0.0.0/{text}")
    except ValueError:
        return BUILTIN_PLACEHOLDERS[BuiltinIgnoreRule.IPV4]
    return text


def _mask_ipv6(match: re.Match[str]) -> str:
    """Mask an IPv6 address candidate if it really is one."""
    text = match.group()
    try:
        ipaddress.IPv6Address(text)
    except ValueError:
        return text
    return BUILTIN_PLACEHOLDERS[BuiltinIgnoreRule.IPV6]


class InvalidIgnorePatternError(ValueError):
    """Raised when an ignore pattern isn't a valid regular expression or exceeds the limits."""


@dataclass(frozen=True)
class VendorRules:
    """Vendor processing rules to apply to a device's config before it's compared."""

    strip_patterns: tuple[str, ...] = ()
    redaction_patterns: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class CompareSide:
    """One of the two configurations to compare."""

    device_name: str
    config: str
    vendor_rules: VendorRules | None = None


@dataclass(frozen=True)
class CompareOptions:
    """What to ignore when comparing."""

    builtin_rules: frozenset[BuiltinIgnoreRule] = frozenset()
    ignore_patterns: tuple[re.Pattern[str], ...] = ()  # Compiled with compile_ignore_patterns()
    ignore_whitespace: bool = False


@dataclass(frozen=True)
class ConfigComparison:
    """Result of comparing two configurations."""

    diff: str  # Unified diff from left to right, starting at the first hunk (empty when nothing differs)
    identical: bool  # Exactly the same, before the ignore options were applied
    lines_only_left: int
    lines_only_right: int

    @property
    def has_differences(self) -> bool:
        """True when differences remain after the ignore options were applied."""
        return bool(self.diff)


class ConfigCompareService:
    """Service for comparing configurations, also across groups (and therefore across repositories)."""

    @staticmethod
    def compile_ignore_patterns(patterns: Sequence[str]) -> tuple[re.Pattern[str], ...]:
        """Compile the custom ignore patterns, blank entries are skipped.

        Raises:
            InvalidIgnorePatternError: If a pattern isn't a valid regular expression or the limits are exceeded
        """
        patterns = [pattern for pattern in patterns if pattern.strip()]
        if len(patterns) > MAX_IGNORE_PATTERNS:
            raise InvalidIgnorePatternError(f"Too many ignore patterns ({len(patterns)}), at most {MAX_IGNORE_PATTERNS} are allowed")

        compiled: list[re.Pattern[str]] = []
        for pattern in patterns:
            if len(pattern) > MAX_IGNORE_PATTERN_LENGTH:
                raise InvalidIgnorePatternError(
                    f"Ignore pattern is too long ({len(pattern)} characters), at most {MAX_IGNORE_PATTERN_LENGTH} are allowed"
                )
            try:
                compiled.append(re.compile(pattern))
            except re.error as ex:
                raise InvalidIgnorePatternError(f"Invalid ignore pattern '{pattern}': {ex}") from ex
        return tuple(compiled)

    @staticmethod
    def resolve_vendor_rules(vendor_id: str, *, apply_strip_patterns: bool, apply_redaction: bool) -> VendorRules:
        """Get the processing rules of a vendor that should be applied before comparing."""
        processing = (get_settings().get_vendor_config(vendor_id) or {}).get("processing") or {}

        strip_patterns: tuple[str, ...] = ()
        if apply_strip_patterns and isinstance(processing.get("strip_patterns"), list):
            strip_patterns = tuple(str(pattern) for pattern in processing["strip_patterns"])

        ### The patterns are used even if redaction.enabled is false, the comparison doesn't change the stored config
        redaction_patterns: tuple[dict[str, Any], ...] = ()
        redaction_cfg = processing.get("redaction")
        if apply_redaction and isinstance(redaction_cfg, dict) and isinstance(redaction_cfg.get("patterns"), list):
            redaction_patterns = tuple(rule for rule in redaction_cfg["patterns"] if isinstance(rule, dict) and rule.get("search"))

        return VendorRules(strip_patterns=strip_patterns, redaction_patterns=redaction_patterns)

    @staticmethod
    def _normalize(config: str) -> str:
        """Use LF line endings and end with exactly one newline, so neither shows up as a difference."""
        text = config.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
        return f"{text}\n" if text else ""

    @staticmethod
    def _redact(config: str, redaction_patterns: Sequence[dict[str, Any]]) -> str:
        """Apply the vendor's redaction rules line by line, leaving lines that were already redacted during the backup alone.

        Redacting such a line again can mangle it, e.g. '^( +password) \\S+' turns ' password <secret hidden>' into
        ' password <secret hidden> hidden>'. A line counts as redacted when it contains the fixed text of one of the
        replacements (e.g. '<secret hidden>'), this also covers backups made before redaction was enabled for a device.
        """
        rules: list[tuple[re.Pattern[str], str]] = []
        placeholders: set[str] = set()
        for rule in redaction_patterns:
            ### Same defaults as apply_processing_rules()
            replacement = str(rule.get("replacement", "<secret hidden>"))
            try:
                rules.append((re.compile(str(rule["search"]), re.MULTILINE), replacement))
            except re.error as ex:
                logger.warning("Invalid redaction search '%s': %s", rule["search"], ex)
                continue
            placeholder = re.sub(r"\\(?:\d+|g<[^>]*>)", "", replacement).strip()
            if placeholder:
                placeholders.add(placeholder)

        lines = config.split("\n")
        for index, line in enumerate(lines):
            if any(placeholder in line for placeholder in placeholders):
                continue
            for pattern, replacement in rules:
                line = pattern.sub(replacement, line)
            lines[index] = line
        return "\n".join(lines)

    def _apply_vendor_rules(self, config: str, vendor_rules: VendorRules | None) -> str:
        """Process the config with the vendor's strip and redaction patterns."""
        if vendor_rules is None:
            return config
        if vendor_rules.strip_patterns:
            config = apply_processing_rules(config, {"strip_patterns": list(vendor_rules.strip_patterns)})
        if vendor_rules.redaction_patterns:
            config = self._redact(config, vendor_rules.redaction_patterns)
        return config

    @staticmethod
    def _device_name_pattern(device_name: str) -> re.Pattern[str] | None:
        """Pattern matching the device's own name (and its short name if it's an FQDN) as a whole word."""
        try:
            ipaddress.ip_address(device_name)
            return None # Devices named after their IP address are covered by the IP rules
        except ValueError:
            pass

        names = {device_name, device_name.split(".")[0]}
        ### Longest first, so an FQDN is masked as a whole instead of only its first label
        names = sorted((name for name in names if len(name) >= MIN_MASKED_DEVICE_NAME_LENGTH), key=len, reverse=True)
        if not names:
            return None
        alternation = "|".join(re.escape(name) for name in names)
        return re.compile(rf"(?<![\w.-])(?:{alternation})(?![\w-])", re.IGNORECASE)

    def _mask_builtin(self, config: str, rules: Collection[BuiltinIgnoreRule], device_name: str) -> str:
        """Replace hostnames, IP and MAC addresses with their placeholders."""
        substitutions: list[tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]]] = []
        if BuiltinIgnoreRule.HOSTNAME in rules:
            hostname_placeholder = BUILTIN_PLACEHOLDERS[BuiltinIgnoreRule.HOSTNAME]
            substitutions.append((_HOSTNAME_STATEMENT, rf"\g<1>{hostname_placeholder}"))
            ### The device's own name also shows up in banners, SNMP locations, descriptions, domain names, ...
            device_name_pattern = self._device_name_pattern(device_name)
            if device_name_pattern is not None:
                substitutions.append((device_name_pattern, hostname_placeholder))
        ### IPv6 first, so an embedded IPv4 address (::ffff:10.0.0.1) is masked as part of the IPv6 address
        if BuiltinIgnoreRule.IPV6 in rules:
            substitutions.append((_IPV6_CANDIDATE, _mask_ipv6))
        if BuiltinIgnoreRule.MAC in rules:
            substitutions.append((_MAC, BUILTIN_PLACEHOLDERS[BuiltinIgnoreRule.MAC]))
        if BuiltinIgnoreRule.IPV4 in rules:
            substitutions.append((_IPV4, _mask_ipv4))

        for pattern, replacement in substitutions:
            config = pattern.sub(replacement, config)
        return config

    @staticmethod
    def _mask_ignored_text(config: str, patterns: Sequence[re.Pattern[str]]) -> str:
        """Replace the text matching any of the custom patterns with the placeholder, line by line.

        Masking the text instead of dropping whole lines keeps the line numbers of the diff correct and still shows
        a line that only one of the configs contains (e.g. an IP address masked in an interface that is missing on the other device).
        """
        if not patterns:
            return config

        ### Empty matches (e.g. from 'x*') would otherwise put a placeholder between every character
        def replace(match: re.Match[str]) -> str:
            return IGNORED_TEXT_PLACEHOLDER if match.group() else ""

        lines = config.split("\n")
        for pattern in patterns:
            lines = [pattern.sub(replace, line) for line in lines]
        return "\n".join(lines)

    def _prepare(self, side: CompareSide, options: CompareOptions) -> str:
        """Apply the vendor rules and the ignore options to a config."""
        config = self._normalize(self._apply_vendor_rules(side.config, side.vendor_rules))
        config = self._mask_builtin(config, options.builtin_rules, side.device_name)
        return self._mask_ignored_text(config, options.ignore_patterns)

    @staticmethod
    def _strip_diff_header(diff: str) -> str:
        """Drop the file header lines before the first hunk, the temporary file names mean nothing to the user."""
        lines = diff.split("\n")
        for index, line in enumerate(lines):
            if line.startswith("@@"):
                return "\n".join(lines[index:])
        ### Only a header without hunks is left when all differences were ignored (e.g. whitespace only)
        return ""

    def _diff_sync(self, left: str, right: str, ignore_whitespace: bool) -> str:
        """Blocking unified diff of two texts.

        git diff --no-index is used instead of difflib: it's much faster on large configs, and the histogram algorithm..
        ..aligns configs with many repeated lines (e.g. '!', 'exit', 'next', 'end') better
        """
        with tempfile.TemporaryDirectory(prefix="kiwissh-compare-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            ### Write LF line endings on Windows too
            (tmp_path / "left.conf").write_text(left, encoding="utf-8", newline="\n")
            (tmp_path / "right.conf").write_text(right, encoding="utf-8", newline="\n")

            options = ["--no-index", "--no-color", "--no-ext-diff", "--histogram", "--unified=3"]
            if ignore_whitespace:
                options += ["--ignore-space-change", "--ignore-blank-lines"]

            ### Exit code 1 only means the files differ
            status, stdout, stderr = Git(tmp_dir).diff(
                *options,
                "--",
                "left.conf",
                "right.conf",
                with_extended_output=True,
                with_exceptions=False,
            )
            if status not in (0, 1):
                raise RuntimeError(f"git diff failed with exit code {status}: {stderr.strip()}")

        return self._strip_diff_header(stdout)

    def _compare_sync(self, left: CompareSide, right: CompareSide, options: CompareOptions) -> ConfigComparison:
        """Blocking comparison of two configurations."""
        if self._normalize(left.config) == self._normalize(right.config):
            return ConfigComparison(diff="", identical=True, lines_only_left=0, lines_only_right=0)

        diff = self._diff_sync(self._prepare(left, options), self._prepare(right, options), options.ignore_whitespace)

        ### The header is stripped, so every line starting with -/+ is a removed/added line
        diff_lines = diff.split("\n") if diff else []
        return ConfigComparison(
            diff=diff,
            identical=False,
            lines_only_left=sum(1 for line in diff_lines if line.startswith("-")),
            lines_only_right=sum(1 for line in diff_lines if line.startswith("+")),
        )

    async def compare(self, left: CompareSide, right: CompareSide, options: CompareOptions) -> ConfigComparison:
        """
        Compare two configurations without blocking the event loop.

        Args:
            left: Configuration shown on the left side (the diff's "removed" lines are only in this one)
            right: Configuration shown on the right side (the diff's "added" lines are only in this one)
            options: What to ignore

        Returns:
            ConfigComparison with the unified diff and the number of lines only one side contains
        """
        return await asyncio.to_thread(self._compare_sync, left, right, options)


### Singleton instance
config_compare_service = ConfigCompareService()
