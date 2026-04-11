"""KiwiSSH application configuration."""

import os
import logging
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


class ApiConfig(BaseModel):
    """API server configuration."""
    host: str = "127.0.0.1"
    port: int = 8000
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
    

### Application configuration models
class AppConfig(BaseModel):
    """Application-level settings."""
    debug: bool = False
    threads: int = Field(default=20, ge=1)
    timeout: int = Field(default=30, ge=1)
    retry: int = Field(default=3, ge=0)
    api: ApiConfig = Field(default_factory=ApiConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)


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


class JumphostBaseConfig(BaseModel):
    """Shared reusable jumphost fields for group and node-level config."""
    hostname: str | None = None
    username: str | None = None
    password: str | None = None
    ssh_key_file: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)

    @field_validator("hostname", "username", "password", "ssh_key_file", mode="before")
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
    port: int = Field(default=22, ge=1, le=65535)

    @field_validator("hostname", "username", mode="before")
    @classmethod
    def validate_required_text(cls, value: str | None) -> str:
        """Enforce non-empty hostname and username for configured group jumphost."""
        text = "" if value is None else str(value).strip()
        if not text:
            raise ValueError("jumphost hostname and username must be non-empty strings")
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
    ssh_key_file: str | None = None
    ssh_profile: str | None = None
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
    def validate_group_ssh_profile(cls, ssh_profile: str | None) -> str:
        """Require a non-empty SSH profile per group."""
        if ssh_profile is None:
            raise ValueError("ssh_profile is required")
        text = str(ssh_profile).strip()
        if not text:
            raise ValueError("ssh_profile must be a non-empty string")
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
    
    @field_validator("password", mode="before")
    @classmethod
    def normalize_group_password(cls, value: str | None) -> str | None:
        """Normalize optional password and convert blanks to None."""
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class NodeConfig(BaseModel):
    """Per-device configuration overrides."""
    username: str | None = None
    password: str | None = None
    ssh_key_file: str | None = None
    ssh_profile: str | None = None
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


class PostgresSourceConfig(BaseModel):
    """PostgreSQL device source."""
    host: str
    port: int = 5432
    database: str
    table: str
    username: str
    password: str


class SourcesConfig(BaseModel):
    """Device source definitions."""
    file: str | None = None
    postgres: PostgresSourceConfig | None = None

    @field_validator("file", mode="before")
    @classmethod
    def validate_file_source_path(cls, value: str | None) -> str | None:
        """Ensure sources.file is absolute when configured (Windows or POSIX)."""
        if value is None:
            return None

        raw_path = str(value).strip()
        expanded_path = os.path.expanduser(raw_path)

        native_path = Path(expanded_path)
        is_native_absolute = native_path.is_absolute()
        is_posix_absolute = PurePosixPath(expanded_path).is_absolute()

        if not is_native_absolute and not is_posix_absolute:
            raise ValueError("sources.file must be an absolute path")

        if is_native_absolute:
            return str(native_path)

        return PurePosixPath(expanded_path).as_posix()


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
    def validate_local_path(cls, local_path: str) -> str:
        """Ensure git.local_path is configured and absolute (Windows or POSIX)."""
        if local_path is None or not str(local_path).strip():
            raise ValueError("git.local_path must be a non-empty path")

        raw_path = str(local_path).strip()
        expanded_path = os.path.expanduser(raw_path)

        native_path = Path(expanded_path)
        is_native_absolute = native_path.is_absolute()
        is_posix_absolute = PurePosixPath(expanded_path).is_absolute()

        if not is_native_absolute and not is_posix_absolute:
            raise ValueError("git.local_path must be an absolute path")

        if is_native_absolute:
            return str(native_path)

        return PurePosixPath(expanded_path).as_posix()


class ApplicationDatabaseConfig(BaseModel):
    """Application PostgreSQL database configuration."""

    host: str
    port: int
    database: str
    username: str
    password: str


class Settings(BaseSettings):
    """Application settings loaded from environment and config files."""

    model_config = SettingsConfigDict(
        env_prefix="KIWISSH_",
        env_file=".env",
        extra="ignore",
    )

    ### Paths
    config_dir: Path = Field(default=Path("/config"))

    ### Testing
    local_test_mode: bool = Field(default=False, description="Use tests/config and tests/sources for local testing")

    ### Configuration sections (loaded from YAML)
    app: AppConfig = Field(default_factory=AppConfig)
    groups: dict[str, GroupConfig] = Field(default_factory=dict)
    nodes: dict[str, NodeConfig] = Field(default_factory=dict)
    sources: SourcesConfig | None = None
    git: GitConfig = Field(default_factory=GitConfig)
    application_database: ApplicationDatabaseConfig | None = None
    schedule: ScheduleConfig | None = None
    api: ApiConfig = Field(default_factory=ApiConfig)

    ### External configs
    ssh_profiles: dict[str, Any] = Field(default_factory=dict)
    vendors: dict[str, dict[str, Any]] = Field(default_factory=dict)

    ### Database URL (computed from application_database config)
    database_url: str = ""

    @field_validator("config_dir", mode="before")
    @classmethod
    def resolve_path(cls, v: str | Path) -> Path:
        """Resolve paths to absolute paths relative to backend directory."""
        return Path(v).resolve()

    @model_validator(mode="after")
    def use_test_config_if_enabled(self) -> "Settings":
        """If LOCAL_TEST_MODE=true, use tests/config for local testing."""
        if self.local_test_mode:
            project_root = Path(__file__).parent.parent.parent.parent

            ### Use test config directory
            test_config_dir = project_root / "tests" / "config"
            if test_config_dir.exists():
                self.config_dir = test_config_dir.resolve()

        return self

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

            ### git
            self.git = GitConfig(**file_content.get("git", {}))

            ### Validate cross-section git remote requirements
            self._validate_git_remote_configuration()

            ### application_database
            self.application_database = ApplicationDatabaseConfig(**file_content.get("application_database", {}))

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
            "timeout": self.app.timeout,
            "retry": self.app.retry,
            "schedule": self.app.schedule,
            "jumphost": None,
        }

        ### Step 1: Apply group-level defaults / overrides
        if group in self.groups:
            group_config = self.groups[group]
            device_config.update({
                "username": group_config.username,
                "password": group_config.password,
                "ssh_key_file": group_config.ssh_key_file,
                "ssh_profile": group_config.ssh_profile,
                "vendor": group_config.vendor,
            })

            ### Materialize group-level jumphost defaults into a mutable dict..
            ## ..so node-level overrides can patch individual keys later
            if group_config.jumphost is not None:
                device_config["jumphost"] = {
                    "hostname": group_config.jumphost.hostname,
                    "port": int(group_config.jumphost.port),
                    "username": group_config.jumphost.username,
                    "password": group_config.jumphost.password,
                    "ssh_key_file": group_config.jumphost.ssh_key_file,
                }

            if group_config.timeout is not None:
                device_config["timeout"] = group_config.timeout
            if group_config.retry is not None:
                device_config["retry"] = group_config.retry
            if group_config.schedule and group_config.schedule.cron is not None:
                device_config["schedule"] = group_config.schedule

        ### Step 2: Apply node-specific overrides
        ### NOTE: Group cannot be overridden here - must be changed in source
        if device_name in self.nodes:
            node_config = self.nodes[device_name]
            if node_config.ssh_profile is not None:
                device_config["ssh_profile"] = node_config.ssh_profile
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
            if node_config.ssh_key_file is not None:
                device_config["ssh_key_file"] = node_config.ssh_key_file

            ### Merge node-level jumphost overrides into group defaults key-by-key
            ## This allows partial node overrides without duplicating the full block
            if node_config.jumphost is not None:
                resolved_jump_host = dict(device_config.get("jumphost") or {})
                if node_config.jumphost.hostname is not None:
                    resolved_jump_host["hostname"] = node_config.jumphost.hostname
                if node_config.jumphost.port is not None:
                    resolved_jump_host["port"] = int(node_config.jumphost.port)
                if node_config.jumphost.username is not None:
                    resolved_jump_host["username"] = node_config.jumphost.username
                if node_config.jumphost.password is not None:
                    resolved_jump_host["password"] = node_config.jumphost.password
                if node_config.jumphost.ssh_key_file is not None:
                    resolved_jump_host["ssh_key_file"] = node_config.jumphost.ssh_key_file
                device_config["jumphost"] = resolved_jump_host or None

            if node_config.schedule and node_config.schedule.cron is not None:
                device_config["schedule"] = node_config.schedule

        ### Validate resolved device auth after group+node merging for optional fields
        resolved_password = str(device_config.get("password") or "").strip()
        resolved_key_file = str(device_config.get("ssh_key_file") or "").strip()

        if not resolved_password and not resolved_key_file:
            raise ValueError(
                f"Device '{device_name}' in group '{group}' requires either password or ssh_key_file"
            )

        ### Validate jumphost details only when jumphost is configured
        jumphost_cfg = device_config.get("jumphost")
        if jumphost_cfg:
            jumphost_name = str(jumphost_cfg.get("hostname") or "").strip()
            jumphost_username = str(jumphost_cfg.get("username") or "").strip()
            jumphost_password = str(jumphost_cfg.get("password") or "").strip()
            jumphost_key_file = str(jumphost_cfg.get("ssh_key_file") or "").strip()

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

            ### Ensure a concrete jumphost port is always available after merge
            jumphost_cfg["port"] = int(jumphost_cfg.get("port") or 22)

        return device_config

@lru_cache  # Last Recently Used cache to store settings instance
def get_settings() -> Settings:
    """Get settings instance or return cached one."""
    settings = Settings()
    settings.load_yaml_configs()
    return settings
