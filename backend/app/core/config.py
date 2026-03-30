"""Project Downtown application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


### Application configuration models
class AppConfig(BaseModel):
    """Application-level settings."""
    debug: bool = False


class GroupConfig(BaseModel):
    """Device group configuration."""
    username: str | None = None
    password: str | None = None
    ssh_profile: str | None = None
    vendor: str | None = None
    timeout: int | None = None


class NodeConfig(BaseModel):
    """Per-device configuration overrides."""
    username: str | None = None
    password: str | None = None
    ssh_profile: str | None = None
    vendor: str | None = None
    timeout: int | None = None


class PostgresSourceConfig(BaseModel):
    """PostgreSQL device source."""
    host: str
    port: int = 5432
    database: str
    user: str
    password: str


class SourcesConfig(BaseModel):
    """Device source definitions."""
    file: str | None = None
    postgres: PostgresSourceConfig | None = None


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


class ScheduleConfig(BaseModel):
    """Backup scheduling configuration."""
    enabled: bool = False
    cron: str | None = None
    timezone: str = "UTC"


class ApiConfig(BaseModel):
    """API server configuration."""
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = Field(default_factory=list)


class Settings(BaseSettings):
    """Application settings loaded from environment and config files."""

    model_config = SettingsConfigDict(
        env_prefix="DOWNTOWN_",
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
        config_file = self.config_dir / "downtown.yaml"
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
                
                ### schedule
                schedule_data = file_content.get("schedule", {})
                if schedule_data:
                    self.schedule = ScheduleConfig(**schedule_data)

                ### Load API configuration
                self.api = ApiConfig(**file_content.get("api", {}))

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
        return self.ssh_profiles.get(profile_name)

    def get_vendor_config(self, vendor_id: str) -> dict[str, Any] | None:
        """Get vendor-specific configuration by ID."""
        return self.vendors.get(vendor_id)

    def _build_database_url(self) -> str:
        """Build application database URL from PostgreSQL configuration.

        Returns:
            SQLAlchemy database URL string
        """

        escaped_user = quote_plus(self.application_database.user)
        escaped_password = quote_plus(self.application_database.password)
        return f"postgresql+psycopg://{escaped_user}:{escaped_password}@{self.application_database.host}:{self.application_database.port}/{self.application_database.database}"

    def get_device_config(self, group: str, device_name: str) -> dict[str, Any]:
        """
        Resolve device configuration with priority: Node-specific > Group defaults

        Group cannot be overridden - it must be changed in the source.
        Returns a dict with resolved ssh_profile, vendor, and other settings.
        """
        device_config = {}

        ### Step 1: Apply group-level defaults
        if group in self.groups:
            group_config = self.groups[group]
            device_config.update({
                "username": group_config.username,
                "password": group_config.password,
                "ssh_profile": group_config.ssh_profile,
                "vendor": group_config.vendor,
                "timeout": group_config.timeout,
            })

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
            if node_config.username is not None:
                device_config["username"] = node_config.username
            if node_config.password is not None:
                device_config["password"] = node_config.password

        return device_config

@lru_cache  # Last Recently Used cache to store settings instance
def get_settings() -> Settings:
    """Get settings instance or return cached one."""
    settings = Settings()
    settings.load_yaml_configs()
    return settings
