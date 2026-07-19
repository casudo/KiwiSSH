"""KiwiSSH application configuration."""

import os
import logging
from enum import Enum
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo
from apscheduler.triggers.cron import CronTrigger

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

### Load .env file early to ensure environment variables are available
load_dotenv()

logger = logging.getLogger(__name__)

SUPPORTED_PROTOCOLS = {"ssh", "telnet"}


def _normalize_protocol(value: str | None, *, allow_none: bool) -> str | None:
    """Normalize protocol value.

    Args:
        value (str | None): The protocol value to normalize
        allow_none (bool): True if None is an acceptable value, e.g. if no protocol override for GroupConfig / NodeConfig

    Raises:
        ValueError: If the protocol value is not supported / empty

    Returns:
        str | None: The normalized protocol value
    """
    if value is None:
        return None if allow_none else "ssh"

    text = str(value).strip().lower()
    if not text:
        if allow_none:
            return None
        raise ValueError("protocol must be 'ssh' or 'telnet'")

    if text not in SUPPORTED_PROTOCOLS:
        raise ValueError("protocol must be 'ssh' or 'telnet'")
    return text


def _resolve_config_dir() -> Path:
    """Resolve the default configuration directory.

    Prefers the Docker mount point `/config` when it exists (container deployments).
    Otherwise falls back to the resolved relative `config` directory on bare metal deployments.

    The location can always be overridden via the `KIWISSH_CONFIG_DIR` environment variable.
    """
    docker_config_dir = Path("/config")
    if docker_config_dir.exists():
        return docker_config_dir

    ### Will resolve three (parents[0,1,2]) directories up from this file
    return Path(__file__).resolve().parents[2] / "config"


### =====================================================================

class ApiConfig(BaseModel):
    """API server configuration."""
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: list[str] = Field(default_factory=list)


class ScheduleConfig(BaseModel):
    """Backup scheduling configuration."""
    cron: str | None = "0 2 * * *"  # Default to daily at 2 AM
    timezone: str = Field(default_factory=lambda: os.environ.get("TZ", "UTC"))
    
    @field_validator("cron", mode="before")
    @classmethod
    def validate_cron(cls, cron: str | None) -> str | None:
        """Validate cron expression format (must have 5 fields).
        
        Valid format: minute hour day month day_of_week
        Example: '0 2 * * *' (daily at 2 AM)
        """
        if cron is None or cron == "":
            return cron
        
        ### Run very basic validation to check for 5 fields
        fields = cron.strip().split()
        if len(fields) != 5:
            raise ValueError(
                f"Invalid cron expression '{cron}': expected 5 fields "
                "(minute hour day month day_of_week), got {len(fields)}. "
                f"Example: '0 2 * * *' for daily at 2 AM"
            )
        
        ### Try to parse with APScheduler to catch other invalid expressions
        try:
            CronTrigger.from_crontab(cron)
        except Exception as e:
            raise ValueError(f"Invalid cron expression '{cron}': {str(e)}")
        
        return cron
    
    @field_validator("timezone", mode="before")
    @classmethod
    def resolve_timezone(cls, tz: str | None) -> str:
        """Use TZ env var if timezone not explicitly provided, otherwise default to UTC."""
        if tz is None or tz == "":
            return os.environ.get("TZ", "UTC")
        return tz
    
    @field_validator("timezone", mode="after")
    @classmethod
    def validate_timezone(cls, tz: str) -> str:
        """Validate timezone is supported by zoneinfo, fallback to UTC if invalid."""
        try:
            ZoneInfo(tz)
        except Exception:
            ### Log warning and fallback to UTC for invalid timezones
            logger.warning(f"Invalid timezone '{tz}', falling back to UTC")
            return "UTC"
        return tz
    

class RetentionConfig(BaseModel):
    """Backup job log retention configuration."""
    enabled: bool = False
    max_rows: int = Field(default=100000, ge=1000, description="Delete oldest jobs when total count exceeds this")
    max_age_days: int = Field(default=90, ge=1, description="Delete jobs older than this many days")


### Application configuration models
class AppConfig(BaseModel):
    """Application-level settings."""
    debug: bool = False
    threads: int = Field(default=20, ge=1)
    timeout: int = Field(default=30, ge=1)
    retry: int = Field(default=3, ge=0)
    protocol: str = "ssh"
    api: ApiConfig = Field(default_factory=ApiConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)

    @field_validator("protocol", mode="before")
    @classmethod
    def validate_protocol(cls, value: str) -> str:
        """Validate default protocol setting."""
        normalized = _normalize_protocol(value, allow_none=False)
        return "ssh" if normalized is None else normalized


class GroupGitRemoteConfig(BaseModel):
    """Optional per-group override for remote git target."""
    url: str | None = None
    branch: str = "main"

    @field_validator("url", mode="before")
    @classmethod
    def normalize_url(cls, url: str | None) -> str | None:
        """Normalize optional URL value by trimming whitespace."""
        if url is None:
            return None
        text = str(url).strip()
        return text or None

    @field_validator("branch", mode="before")
    @classmethod
    def normalize_branch(cls, branch: str | None) -> str:
        """Normalize branch value by trimming whitespace and defaulting to main."""
        if branch is None:
            return "main"
        text = str(branch).strip()
        return text or "main"


class GroupGitConfig(BaseModel):
    """Optional per-group git configuration overrides."""
    commit_message_template: str | None = None
    remote: GroupGitRemoteConfig | None = None

    @field_validator("commit_message_template", mode="before")
    @classmethod
    def normalize_commit_message_template(cls, template: str | None) -> str | None:
        """Normalize optional commit message template value by trimming whitespace."""
        if template is None:
            return None
        text = str(template).strip()
        return text or None


class NodeGitConfig(BaseModel):
    """Optional per-node git configuration overrides."""
    commit_message_template: str | None = None
    # TODO: Maybe add remote URL override in the future?

    @field_validator("commit_message_template", mode="before")
    @classmethod
    def normalize_commit_message_template(cls, template: str | None) -> str | None:
        """Normalize optional commit message template value by trimming whitespace."""
        if template is None:
            return None
        text = str(template).strip()
        return text or None


### =====================================================================
### Notification Configuration

class NotificationTrigger(str, Enum):
    """Controls when backup notifications are sent."""
    ALWAYS = "always"                     # Notify on every Success or Failed
    FAILURE = "failure"                   # Notify on every Failed
    FAILURE_NEW = "failure_new"           # Notify on Failed **ONLY** when previous was Success, No Changes or None (first ever backup failure)


class SmtpConfig(BaseModel):
    """SMTP server configuration for email notifications."""
    host: str
    port: int = Field(default=25, ge=1, le=65535)
    sender: str
    recipients: list[str] = Field(default_factory=list)
    username: str | None = None
    password: str | None = None
    use_tls: bool = False # STARTTLS (typically port 587)
    use_ssl: bool = False # Direct SSL/TLS (typically port 465)

    @field_validator("host", "sender", mode="before")
    @classmethod
    def validate_non_empty_text(cls, value: str | None) -> str:
        """Require non-empty strings for host and sender."""
        text = "" if value is None else str(value).strip()
        if not text:
            raise ValueError("notifications.smtp host and sender must be non-empty strings")
        return text

    @field_validator("recipients", mode="before")
    @classmethod
    def validate_recipients(cls, value: list | None) -> list[str]:
        """Require at least one recipient address."""
        if not value:
            raise ValueError("notifications.smtp.recipients must contain at least one address")
        cleaned = [str(r).strip() for r in value if str(r).strip()]
        if not cleaned:
            raise ValueError("notifications.smtp.recipients must contain at least one address")
        return cleaned

    @model_validator(mode="after")
    def validate_tls_ssl_exclusive(self) -> "SmtpConfig":
        """Ensure use_tls and use_ssl are not both enabled simultaneously."""
        if self.use_tls and self.use_ssl:
            raise ValueError("notifications.smtp: use_tls and use_ssl cannot both be true")
        return self


class NotificationType(BaseModel):
    """Notification delivery channel."""
    smtp: SmtpConfig | None = None
    # TODO: webhook, slack, teams, ...


class NotificationsConfig(BaseModel):
    """Global notification configuration."""
    enabled: bool = False
    trigger: NotificationTrigger = NotificationTrigger.FAILURE
    type: NotificationType = Field(default_factory=NotificationType)
    large_diff_threshold: int = Field(
        default=500,
        ge=1,
        description="Send a major change notification when lines added or removed reaches this threshold. Set to a very high number to effectively disable.",
    )

    @model_validator(mode="after")
    def validate_type_config(self) -> "NotificationsConfig":
        """Require at least one channel config block when notifications are enabled."""
        if not self.enabled:
            return self
        if self.type.smtp is None:
            raise ValueError(
                "At least one notification channel must be configured under notifications.type "
                "(e.g. notifications.type.smtp) when notifications.enabled is true"
            )
        ### TODO: Update check for multiple channels
        return self


### =====================================================================

class JumphostBaseConfig(BaseModel):
    """Shared reusable jumphost fields for group and node-level config."""
    hostname: str | None = None
    username: str | None = None
    password: str | None = None
    ssh_key_file: str | None = None
    ssh_profile: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)

    @field_validator("hostname", "username", "password", "ssh_key_file", "ssh_profile", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Normalize optional string values and convert blanks to None."""
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class GroupJumphostConfig(JumphostBaseConfig):
    """Group-level jumphost defaults applied to all devices in the group."""
    hostname: str
    username: str
    ssh_profile: str
    port: int = Field(default=22, ge=1, le=65535)

    @field_validator("hostname", "username", "ssh_profile", mode="before")
    @classmethod
    def validate_required_text(cls, value: str | None) -> str:
        """Enforce non-empty required strings for configured group jumphost."""
        text = "" if value is None else str(value).strip()
        if not text:
            raise ValueError("jumphost hostname, username, and ssh_profile must be non-empty strings")
        return text

    @model_validator(mode="after")
    def validate_group_jumphost_auth(self) -> "GroupJumphostConfig":
        """Require at least one auth method for group-level jumphost config."""
        if not self.password and not self.ssh_key_file:
            raise ValueError(
                "groups.<group>.jumphost requires either 'password' or 'ssh_key_file'"
            )
        return self


class NodeJumphostConfig(JumphostBaseConfig):
    """Node-level jumphost overrides (all fields optional for partial override)."""


class GroupConfig(BaseModel):
    """Device group configuration."""
    username: str
    password: str | None = None
    enable_password: str | None = None
    ssh_key_file: str | None = None
    ssh_profile: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    protocol: str | None = None
    vendor: str
    jumphost: GroupJumphostConfig | None = None
    timeout: int | None = Field(default=None, ge=1)
    retry: int | None = Field(default=None, ge=0)
    schedule: ScheduleConfig | None = None
    git: GroupGitConfig | None = None

    @field_validator("username", mode="before")
    @classmethod
    def validate_group_username(cls, value: str | None) -> str:
        """Require a non-empty SSH username per group."""
        text = "" if value is None else str(value).strip()
        if not text:
            raise ValueError("username is required and must be a non-empty string")
        return text

    @field_validator("ssh_key_file", mode="before")
    @classmethod
    def normalize_group_key_file(cls, value: str | None) -> str | None:
        """Normalize optional SSH key file path and convert blanks to None."""
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("ssh_profile", mode="before")
    @classmethod
    def normalize_group_ssh_profile(cls, ssh_profile: str | None) -> str | None:
        """Normalize optional SSH profile and reject blanks."""
        if ssh_profile is None:
            return None
        text = str(ssh_profile).strip()
        if not text:
            raise ValueError("ssh_profile must be a non-empty string when provided")
        return text

    @field_validator("vendor", mode="before")
    @classmethod
    def validate_vendor(cls, vendor: str) -> str:
        """Require a non-empty vendor id per group."""
        if vendor is None:
            raise ValueError("Vendor is required")
        text = str(vendor).strip()
        if not text:
            raise ValueError("Vendor must be a non-empty string")
        return text

    @field_validator("protocol", mode="before")
    @classmethod
    def validate_protocol(cls, value: str | None) -> str | None:
        """Normalize optional protocol override."""
        return _normalize_protocol(value, allow_none=True)

    @model_validator(mode="after")
    def validate_group_protocol(self) -> "GroupConfig":
        """Require ssh_profile unless protocol is explicitly telnet."""
        if self.protocol == "telnet":
            return self
        if not self.ssh_profile:
            raise ValueError("ssh_profile is required for SSH protocol")
        return self
    
    @field_validator("password", mode="before")
    @classmethod
    def normalize_group_password(cls, value: str | None) -> str | None:
        """Normalize optional password and convert blanks to None."""
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("enable_password", mode="before")
    @classmethod
    def normalize_group_enable_password(cls, value: str | None) -> str | None:
        """Normalize optional enable password and convert blanks to None."""
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class NodeConfig(BaseModel):
    """Per-device configuration overrides."""
    username: str | None = None
    password: str | None = None
    enable_password: str | None = None
    ssh_key_file: str | None = None
    ssh_profile: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    protocol: str | None = None
    vendor: str | None = None
    jumphost: NodeJumphostConfig | None = None
    timeout: int | None = Field(default=None, ge=1)
    retry: int | None = Field(default=None, ge=0)
    schedule: ScheduleConfig | None = None
    git: NodeGitConfig | None = None

    @field_validator("username", "password", mode="before")
    @classmethod
    def normalize_node_auth_text(cls, value: str | None) -> str | None:
        """Normalize optional auth strings and convert blanks to None."""
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("enable_password", mode="before")
    @classmethod
    def normalize_node_enable_password(cls, value: str | None) -> str | None:
        """Normalize optional enable password and convert blanks to None."""
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("ssh_key_file", mode="before")
    @classmethod
    def normalize_node_key_file(cls, value: str | None) -> str | None:
        """Normalize optional SSH key file path and convert blanks to None."""
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("ssh_profile", mode="before")
    @classmethod
    def validate_node_ssh_profile(cls, ssh_profile: str | None) -> str | None:
        """Normalize optional node SSH profile and reject blanks."""
        if ssh_profile is None:
            return None
        text = str(ssh_profile).strip()
        if not text:
            raise ValueError("ssh_profile must be a non-empty string when provided")
        return text

    @field_validator("vendor", mode="before")
    @classmethod
    def validate_vendor(cls, vendor: str | None) -> str | None:
        """Normalize optional node vendor and reject blank values."""
        if vendor is None:
            return None
        text = str(vendor).strip()
        if not text:
            raise ValueError("Vendor must be a non-empty string when provided")
        return text

    @field_validator("protocol", mode="before")
    @classmethod
    def validate_protocol(cls, value: str | None) -> str | None:
        """Normalize optional protocol override."""
        return _normalize_protocol(value, allow_none=True)


class PostgresSourceConfig(BaseModel):
    """PostgreSQL device source."""
    host: str
    port: int = Field(default=5432, ge=1, le=65535)
    database: str
    table: str
    username: str
    password: str

    @field_validator("host", "database", "table", "username", "password", mode="before")
    @classmethod
    def validate_non_empty_text(cls, value: str | None) -> str:
        """Require non-empty strings for PostgreSQL source connection fields."""
        text = "" if value is None else str(value).strip()
        if not text:
            raise ValueError("postgres source connection fields must be non-empty strings")
        return text


class HttpSourceConfig(BaseModel):
    """Generic HTTP device source.

    Fetches a JSON list of devices from an HTTP(S) endpoint and maps each item onto the source fields used by KiwiSSH.
    Vendor, credentials and SSH profile are still resolved from the matching group/node config in `kiwissh.yaml`.
    """
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    map: dict[str, str] = Field(default_factory=dict) # Maps KiwiSSH field -> field name in the JSON response
    default_group: str | None = None # Fallback group when a response item has no (mapped) group value
    items_key: str | None = None # Optional key to locate the device list when the response is an object
    verify_tls: bool = True
    timeout: int = Field(default=10, ge=1)

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, value: str | None) -> str:
        """Require an http(s) URL for the HTTP source."""
        text = "" if value is None else str(value).strip()
        if not text:
            raise ValueError("sources.http.url must be a non-empty string")
        if not (text.startswith("http://") or text.startswith("https://")):
            raise ValueError("sources.http.url must start with 'http://' or 'https://'")
        return text

    @field_validator("headers", mode="before")
    @classmethod
    def normalize_headers(cls, value: dict | None) -> dict[str, str]:
        """Coerce header keys/values to strings and drop blanks."""
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("sources.http.headers must be a mapping of header name to value")
        return {str(k).strip(): str(v) for k, v in value.items() if str(k).strip()}

    @field_validator("map", mode="before")
    @classmethod
    def normalize_map(cls, value: dict | None) -> dict[str, str]:
        """Validate the field map keys against the supported canonical fields."""
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("sources.http.map must be a mapping of canonical field to JSON field")
        allowed = {"device_name", "ip_address", "group", "enabled"}
        
        normalized: dict[str, str] = {}
        for key, mapped in value.items():
            canonical = str(key).strip()
            if canonical not in allowed:
                raise ValueError(
                    f"sources.http.map contains unsupported field '{canonical}'. "
                    f"Allowed fields: {', '.join(sorted(allowed))}"
                )
            mapped_field = str(mapped).strip()
            if mapped_field:
                normalized[canonical] = mapped_field
        return normalized

    @field_validator("default_group", "items_key", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Normalize optional text fields and convert blanks to None."""
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class SourcesConfig(BaseModel):
    """Device source definitions."""
    file: str | None = None
    ansible: str | None = None
    postgres: PostgresSourceConfig | None = None
    http: HttpSourceConfig | None = None

    @field_validator("file", "ansible", mode="before")
    @classmethod
    def normalize_file_source_path(cls, value: str | None) -> str | None:
        """Normalize file sources.

        Accepts absolute or relative paths.
        Relative paths are resolved against the configuration directory later (Settings._resolve_config_relative_path).
        """
        if value is None:
            return None

        raw_path = str(value).strip()
        if not raw_path:
            return None
        return os.path.expanduser(raw_path)

    @model_validator(mode="after")
    def validate_exactly_one_source(self) -> "SourcesConfig":
        """Require exactly one configured device source: file, ansible, postgres or http."""
        configured = [
            name
            for name, value in (
                ("file", self.file),
                ("ansible", self.ansible),
                ("postgres", self.postgres),
                ("http", self.http),
            )
            if value is not None
        ]

        if len(configured) > 1:
            raise ValueError(
                "Configure only one source under 'sources': one of 'file', 'ansible', 'postgres' or 'http', "
                f"not multiple ({', '.join(configured)})"
            )

        if not configured:
            raise ValueError(
                "One source is required under 'sources': configure either 'file', 'ansible', 'postgres' or 'http'"
            )

        return self


### Git Configuration
class GitRemoteConfig(BaseModel):
    """Git remote repository configuration."""
    url: str | None = None
    branch: str = "main"

    @field_validator("url", mode="before")
    @classmethod
    def normalize_url(cls, url: str | None) -> str | None:
        """Normalize optional URL values by trimming whitespace."""
        if url is None:
            return None
        text = str(url).strip()
        return text or None

    @field_validator("branch", mode="before")
    @classmethod
    def normalize_branch(cls, branch: str | None) -> str:
        """Normalize branch value by trimming whitespace and defaulting to main."""
        if branch is None:
            return "main"
        text = str(branch).strip()
        return text or "main"

    @model_validator(mode="after")
    def validate_remote(self) -> "GitRemoteConfig":
        """Validate required fields when git.remote is configured."""
        if self.url is None:
            raise ValueError("git.remote.url is required when git.remote is configured")
        return self


class GitConfig(BaseModel):
    """Git repository settings."""
    local_path: str = "/config/backups"
    commit_message_template: str = "Backup: {group}/{device_name} at {timestamp}"
    remote: GitRemoteConfig | None = None

    @field_validator("local_path", mode="before")
    @classmethod
    def normalize_local_path(cls, local_path: str) -> str:
        """Normalize git.local_path.

        Accepts absolute or relative paths.
        Relative paths are resolved against the configuration directory later (Settings._resolve_config_relative_path).
        """
        if local_path is None or not str(local_path).strip():
            raise ValueError("git.local_path must be a non-empty path")
        return os.path.expanduser(str(local_path).strip())


class ApplicationDatabaseConfig(BaseModel):
    """Application database configuration.

    Supports backends selected via `type`:
      - `postgresql` (default): requires host/database/username/password.
      - `sqlite`: file-based, requires only `path`.
    """

    type: str = "postgresql"

    ### PostgreSQL connection fields (required when type == "postgresql")
    host: str | None = None
    port: int = Field(default=5432, ge=1, le=65535)
    database: str | None = None
    username: str | None = None
    password: str | None = None

    ### SQLite connection field (required when type == "sqlite")
    path: str | None = None

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: str | None) -> str:
        """Normalize and validate the database backend type."""
        text = ("postgresql" if value is None else str(value)).strip().lower()
        if text not in {"postgresql", "sqlite"}:
            raise ValueError("application_database.type must be 'postgresql' or 'sqlite'")
        return text

    @model_validator(mode="after")
    def validate_required_fields(self) -> "ApplicationDatabaseConfig":
        """Ensure the fields required for the selected backend are provided."""
        if self.type == "postgresql":
            missing = [
                name
                for name in ("host", "database", "username", "password")
                if not (getattr(self, name) or "").strip()
            ]
            if missing:
                raise ValueError(
                    "application_database PostgreSQL connection fields must be non-empty: "
                    + ", ".join(missing)
                )
        elif self.type == "sqlite":
            if not (self.path or "").strip():
                raise ValueError(
                    "application_database.path must be a non-empty file path when type is 'sqlite'"
                )
        return self


class Settings(BaseSettings):
    """Application settings loaded from environment and config files."""

    model_config = SettingsConfigDict(
        env_prefix="KIWISSH_",
        env_file=".env",
        extra="ignore",
    )

    ### Paths
    config_dir: Path = Field(default_factory=_resolve_config_dir)

    ### Testing
    local_test_mode: bool = Field(default=False, description="Enforce config values for easier local testing")

    ### Configuration sections (loaded from YAML)
    app: AppConfig = Field(default_factory=AppConfig)
    groups: dict[str, GroupConfig] = Field(default_factory=dict)
    nodes: dict[str, NodeConfig] = Field(default_factory=dict)
    sources: SourcesConfig | None = None
    git: GitConfig = Field(default_factory=GitConfig)
    application_database: ApplicationDatabaseConfig | None = None
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    schedule: ScheduleConfig | None = None
    api: ApiConfig = Field(default_factory=ApiConfig)

    ### External configs
    ssh_profiles: dict[str, Any] = Field(default_factory=dict)
    vendors: dict[str, dict[str, Any]] = Field(default_factory=dict)

    ### Database URL (computed from application_database config)
    database_url: str = ""


    @model_validator(mode="after")
    def use_test_config_if_enabled(self) -> "Settings":
        """If LOCAL_TEST_MODE=true, use the default config location for local testing."""
        if self.local_test_mode:
            self.config_dir = _resolve_config_dir()

        return self

    def _resolve_config_relative_path(self, path_value: str) -> str:
        """Resolve a possibly-relative path against the configuration directory.

        Absolute paths (native or POSIX-style like '/config/backups') are returned
        unchanged. Relative paths are resolved against `config_dir` so bare-metal
        installs work without hardcoded absolute paths.
        """
        expanded = os.path.expanduser(str(path_value).strip())
        candidate = Path(expanded)
        ### Check and return absolute path
        if candidate.is_absolute() or PurePosixPath(expanded).is_absolute():
            return str(candidate)
        ### return resolved relative path
        return str((self.config_dir / candidate).resolve())

    def load_yaml_configs(self) -> None:
        """Load YAML configuration files."""
        ### Load main config
        config_file = self.config_dir / "kiwissh.yaml"
        if not config_file.exists():
            raise ValueError(f"Main configuration file not found: {config_file}.")

        with open(config_file, encoding="utf-8") as f:
            file_content = yaml.safe_load(f) or {}

            ### TODO: Check for required sections and handle missing sections gracefully with defaults or warnings

            ### app
            self.app = AppConfig(**file_content.get("app", {}))

            ### groups
            groups_data = file_content.get("groups", {})
            self.groups = {name: GroupConfig(**cfg) for name, cfg in groups_data.items()}

            ### nodes
            nodes_data = file_content.get("nodes", {})
            self.nodes = {name: NodeConfig(**cfg) for name, cfg in nodes_data.items()}

            ### sources
            self.sources = SourcesConfig(**file_content.get("sources", {}))
            ## Resolve a relative sources.file path against the configuration directory
            if self.sources.file:
                self.sources.file = self._resolve_config_relative_path(self.sources.file)

            ### git
            self.git = GitConfig(**file_content.get("git", {}))
            ## Resolve a relative git.local_path against the configuration directory
            self.git.local_path = self._resolve_config_relative_path(self.git.local_path)

            ### Validate cross-section git remote requirements
            self._validate_git_remote_configuration()

            ### application_database
            self.application_database = ApplicationDatabaseConfig(**file_content.get("application_database", {}))

            ### notifications
            self.notifications = NotificationsConfig(**file_content.get("notifications", {}))

        ### Load SSH profiles
        ssh_profiles_file = self.config_dir / "ssh_profiles.yaml"
        if ssh_profiles_file.exists():
            with open(ssh_profiles_file, encoding="utf-8") as f:
                self.ssh_profiles = yaml.safe_load(f) or {}

        ### Load vendor configs
        vendors_dir = self.config_dir / "vendors"
        if vendors_dir.exists():
            for vendor_file in vendors_dir.glob("*.yaml"):
                with open(vendor_file, encoding="utf-8") as f:
                    vendor_data = yaml.safe_load(f) or {}
                    vendor_id = vendor_data["vendor"].get("id")
                    self.vendors[vendor_id] = vendor_data

        ### Build application database URL from application_database config.
        self.database_url = self._build_database_url()

    def get_ssh_profile(self, profile_name: str) -> dict[str, Any] | None:
        """Get SSH profile configuration by name."""
        profiles = self.ssh_profiles.get("profiles")
        if not isinstance(profiles, dict):
            return None
        return profiles.get(profile_name)

    def get_vendor_config(self, vendor_id: str) -> dict[str, Any] | None:
        """Get vendor-specific configuration by ID."""
        return self.vendors.get(vendor_id)

    def _validate_git_remote_configuration(self) -> None:
        """Validate global and group-level git remote URL requirements."""
        if self.git.remote is not None:
            return

        invalid_groups = [
            group_name
            for group_name, group_cfg in self.groups.items()
            if group_cfg.git is not None
            and group_cfg.git.remote is not None
            and group_cfg.git.remote.url is None
        ] # If no URL is configured

        if invalid_groups:
            raise ValueError(
                "groups.<group>.git.remote.url is required when no global git.remote.url is configured. "
                f"Missing URL for groups: {', '.join(invalid_groups)}"
            )

    def _build_database_url(self) -> str:
        """Build application database URL from PostgreSQL configuration.

        Returns:
            SQLAlchemy database URL string
        """
        if self.application_database is None:
            raise ValueError("Missing required 'application_database' section in kiwissh.yaml")

        return self._build_postgres_url(
            host=self.application_database.host,
            port=self.application_database.port,
            database=self.application_database.database,
            user=self.application_database.username,
            password=self.application_database.password,
        )

    @staticmethod
    def _build_postgres_url(*, host: str, port: int, database: str, user: str, password: str) -> str:
        """Build a SQLAlchemy PostgreSQL URL from raw connection fields."""

        escaped_user = quote_plus(user)
        escaped_password = quote_plus(password)
        return f"postgresql+psycopg://{escaped_user}:{escaped_password}@{host}:{port}/{database}"

    def get_source_postgres_url(self) -> str | None:
        """Build PostgreSQL URL for device source when configured."""
        return self._build_postgres_url(
            host=self.sources.postgres.host,
            port=self.sources.postgres.port,
            database=self.sources.postgres.database,
            user=self.sources.postgres.username,
            password=self.sources.postgres.password,
        )

    def get_device_config(self, group: str, device_name: str) -> dict[str, Any]:
        """
        Resolve device configuration with priority: App defaults < Group defaults < Node-specific

        Group cannot be overridden - it must be changed in the source.
        Returns a dict with resolved ssh_profile, vendor, and other settings.
        """
        ### Step 0: Start with application-level defaults
        device_config = {
            "port": 22,
            "timeout": self.app.timeout,
            "retry": self.app.retry,
            "schedule": self.app.schedule,
            "jumphost": None,
            "protocol": self.app.protocol,
        }
        port_is_default = True

        ### Step 1: Apply group-level defaults / overrides
        if group in self.groups:
            group_config = self.groups[group]
            device_config.update({
                "username": group_config.username,
                "password": group_config.password,
                "enable_password": group_config.enable_password,
                "ssh_key_file": group_config.ssh_key_file,
                "ssh_profile": group_config.ssh_profile,
                "vendor": group_config.vendor,
            })

            ### Materialize group-level jumphost defaults into a mutable dict..
            ## ..so node-level overrides can patch individual keys later
            if group_config.jumphost is not None:
                device_config["jumphost"] = {
                    "hostname": group_config.jumphost.hostname,
                    "port": group_config.jumphost.port,
                    "username": group_config.jumphost.username,
                    "password": group_config.jumphost.password,
                    "ssh_key_file": group_config.jumphost.ssh_key_file,
                    "ssh_profile": group_config.jumphost.ssh_profile,
                }

            if group_config.timeout is not None:
                device_config["timeout"] = group_config.timeout
            if group_config.retry is not None:
                device_config["retry"] = group_config.retry
            if group_config.schedule and group_config.schedule.cron is not None:
                device_config["schedule"] = group_config.schedule
            if group_config.port is not None:
                device_config["port"] = group_config.port
                port_is_default = False
            if group_config.protocol is not None:
                device_config["protocol"] = group_config.protocol

        ### Step 2: Apply node-specific overrides
        ### NOTE: Group cannot be overridden here - must be changed in source
        if device_name in self.nodes:
            node_config = self.nodes[device_name]
            if node_config.ssh_profile is not None:
                device_config["ssh_profile"] = node_config.ssh_profile
            if node_config.port is not None:
                device_config["port"] = node_config.port
                port_is_default = False
            if node_config.protocol is not None:
                device_config["protocol"] = node_config.protocol
            if node_config.vendor is not None:
                device_config["vendor"] = node_config.vendor
            if node_config.timeout is not None:
                device_config["timeout"] = node_config.timeout
            if node_config.retry is not None:
                device_config["retry"] = node_config.retry
            if node_config.username is not None:
                device_config["username"] = node_config.username
            if node_config.password is not None:
                device_config["password"] = node_config.password
            if node_config.enable_password is not None:
                device_config["enable_password"] = node_config.enable_password
            if node_config.ssh_key_file is not None:
                device_config["ssh_key_file"] = node_config.ssh_key_file

            ### Merge node-level jumphost overrides into group defaults key-by-key
            ## This allows partial node overrides without duplicating the full block
            if node_config.jumphost is not None:
                resolved_jump_host = dict(device_config.get("jumphost") or {})
                if node_config.jumphost.hostname is not None:
                    resolved_jump_host["hostname"] = node_config.jumphost.hostname
                if node_config.jumphost.port is not None:
                    resolved_jump_host["port"] = node_config.jumphost.port
                if node_config.jumphost.username is not None:
                    resolved_jump_host["username"] = node_config.jumphost.username
                if node_config.jumphost.password is not None:
                    resolved_jump_host["password"] = node_config.jumphost.password
                if node_config.jumphost.ssh_key_file is not None:
                    resolved_jump_host["ssh_key_file"] = node_config.jumphost.ssh_key_file
                if node_config.jumphost.ssh_profile is not None:
                    resolved_jump_host["ssh_profile"] = node_config.jumphost.ssh_profile
                device_config["jumphost"] = resolved_jump_host or None

            if node_config.schedule and node_config.schedule.cron is not None:
                device_config["schedule"] = node_config.schedule

        ### Validate resolved device auth after group+node merging for optional fields
        resolved_protocol = str(device_config.get("protocol")).strip().lower()
        if resolved_protocol not in SUPPORTED_PROTOCOLS:
            raise ValueError(f"protocol must be one of {SUPPORTED_PROTOCOLS}")
        device_config["protocol"] = resolved_protocol

        if resolved_protocol == "telnet" and port_is_default:
            device_config["port"] = 23

        resolved_password = str(device_config.get("password") or "").strip()
        resolved_key_file = str(device_config.get("ssh_key_file") or "").strip()

        if resolved_protocol == "telnet":
            if not resolved_password:
                raise ValueError(
                    f"Device '{device_name}' in group '{group}' requires password for telnet protocol"
                )
            if device_config.get("jumphost") is not None:
                raise ValueError(
                    f"Device '{device_name}' in group '{group}' uses telnet protocol which does not support jumphost"
                )
        elif resolved_protocol == "ssh":
            if not resolved_password and not resolved_key_file:
                raise ValueError(
                    f"Device '{device_name}' in group '{group}' requires either password or ssh_key_file"
                )
            resolved_profile = str(device_config.get("ssh_profile") or "").strip()
            if not resolved_profile:
                raise ValueError(
                    f"Device '{device_name}' in group '{group}' requires ssh_profile for SSH protocol"
                )
            device_config["ssh_profile"] = resolved_profile

        ### Validate jumphost details only when jumphost is configured
        jumphost_cfg = device_config.get("jumphost")
        if jumphost_cfg:
            jumphost_name = str(jumphost_cfg.get("hostname") or "").strip()
            jumphost_username = str(jumphost_cfg.get("username") or "").strip()
            jumphost_password = str(jumphost_cfg.get("password") or "").strip()
            jumphost_key_file = str(jumphost_cfg.get("ssh_key_file") or "").strip()
            jumphost_ssh_profile = str(jumphost_cfg.get("ssh_profile") or "").strip()

            if not jumphost_name:
                raise ValueError(
                    f"Device '{device_name}' in group '{group}' has jumphost config without hostname"
                )
            if not jumphost_username:
                raise ValueError(
                    f"Device '{device_name}' in group '{group}' has jumphost config without username"
                )
            if not jumphost_password and not jumphost_key_file:
                raise ValueError(
                    f"Device '{device_name}' in group '{group}' jumphost requires either password or ssh_key_file"
                )
            if not jumphost_ssh_profile:
                raise ValueError(
                    f"Device '{device_name}' in group '{group}' jumphost requires ssh_profile"
                )

            ### Keep normalized profile text in resolved config for SSHService consumption
            jumphost_cfg["ssh_profile"] = jumphost_ssh_profile

            ### Ensure a concrete jumphost port is always available after merge
            jumphost_cfg["port"] = int(jumphost_cfg.get("port") or 22)

        return device_config

@lru_cache  # Last Recently Used cache to store settings instance
def get_settings() -> Settings:
    """Get settings instance or return cached one."""
    settings = Settings()
    settings.load_yaml_configs()
    return settings
