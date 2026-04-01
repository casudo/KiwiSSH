"""KiwiSSH application configuration."""

import os
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo
from apscheduler.triggers.cron import CronTrigger

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file early to ensure environment variables are available
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


class GroupConfig(BaseModel):
    """Device group configuration."""
    username: str | None = None
    password: str | None = None
    ssh_profile: str | None = None
    vendor: str | None = None
    timeout: int | None = Field(default=None, ge=1)
    retry: int | None = Field(default=None, ge=0)
    schedule: ScheduleConfig | None = None


class NodeConfig(BaseModel):
    """Per-device configuration overrides."""
    username: str | None = None
    password: str | None = None
    ssh_profile: str | None = None
    vendor: str | None = None
    timeout: int | None = Field(default=None, ge=1)
    retry: int | None = Field(default=None, ge=0)
    schedule: ScheduleConfig | None = None


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
        """Ensure sources.file is absolute when configured."""
        if value is None:
            return None

        raw_path = str(value).strip()
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            raise ValueError("sources.file must be an absolute path")

        return str(path)


### Git Configuration
class GitRemoteConfig(BaseModel):
    """Git remote repository configuration."""
    enabled: bool = False
    url: str | None = None
    branch: str = "main"
    push_after_commit: bool = False


class GitConfig(BaseModel):
    """Git repository settings."""
    local_path: str = "./backups"
    auto_commit: bool = True
    commit_message_template: str = "Backup: {device_name} at {timestamp}"
    remote: GitRemoteConfig | None = None


class ApplicationDatabaseConfig(BaseModel):
    """Application PostgreSQL database configuration."""

    host: str
    port: int
    database: str
    user: str
    password: str


class Settings(BaseSettings):
    """Application settings loaded from environment and config files."""

    model_config = SettingsConfigDict(
        env_prefix="KIWISSH_",
        env_file=".env",
        extra="ignore",
    )

    ### Paths
    config_dir: Path = Field(default=Path("../config"))
    backups_dir: Path = Field(default=Path("../backups"))

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

    @field_validator("config_dir", "backups_dir", mode="before")
    @classmethod
    def resolve_path(cls, v: str | Path) -> Path:
        """Resolve paths to absolute paths relative to backend directory."""
        return Path(v).resolve()

    @model_validator(mode="after")
    def use_test_config_if_enabled(self) -> "Settings":
        """If LOCAL_TEST_MODE=true, use tests/config and tests/backups for local testing."""
        if self.local_test_mode:
            project_root = Path(__file__).parent.parent.parent.parent

            ### Use test config directory
            test_config_dir = project_root / "tests" / "config"
            if test_config_dir.exists():
                self.config_dir = test_config_dir.resolve()

            ### Use test backups directory
            test_backups_dir = project_root / "tests" / "backups"
            test_backups_dir.mkdir(parents=True, exist_ok=True)
            self.backups_dir = test_backups_dir.resolve()
        else:
            ### Production mode: backups next to config in project root
            project_root = Path(__file__).parent.parent.parent.parent
            prod_backups_dir = project_root / "backups"
            self.backups_dir = prod_backups_dir.resolve()

        return self

    def load_yaml_configs(self) -> None:
        """Load YAML configuration files."""
        ### Load main config
        config_file = self.config_dir / "kiwissh.yaml"
        if config_file.exists():
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

    def _build_database_url(self) -> str:
        """Build application database URL from PostgreSQL configuration.

        Returns:
            SQLAlchemy database URL string
        """
        return self._build_postgres_url(
            host=self.application_database.host,
            port=self.application_database.port,
            database=self.application_database.database,
            user=self.application_database.user,
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
            "schedule": self.app.schedule
        }

        ### Step 1: Apply group-level defaults / overrides
        if group in self.groups:
            group_config = self.groups[group]
            device_config.update({
                "username": group_config.username,
                "password": group_config.password,
                "ssh_profile": group_config.ssh_profile,
                "vendor": group_config.vendor,
            })
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
            if node_config.schedule and node_config.schedule.cron is not None:
                device_config["schedule"] = node_config.schedule

        return device_config

@lru_cache  # Last Recently Used cache to store settings instance
def get_settings() -> Settings:
    """Get settings instance or return cached one."""
    settings = Settings()
    settings.load_yaml_configs()
    return settings
