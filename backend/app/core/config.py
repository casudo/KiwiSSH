"""Project Downtown application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    ### API settings
    # api_host: str = "127.0.0.1"
    api_port: int = 8000
    debug: bool = True

    ### Testing
    local_test_mode: bool = Field(default=False, description="Use tests/config and tests/sources for local testing")

    ### Loaded from YAML files
    app_config: dict[str, Any] = Field(default_factory=dict)
    ssh_profiles: dict[str, Any] = Field(default_factory=dict)
    vendors: dict[str, dict[str, Any]] = Field(default_factory=dict)
    nodes_config: dict[str, Any] = Field(default_factory=dict)
    backup_storage_config: dict[str, Any] = Field(default_factory=dict)

    ### Database URL (computed from backup_storage_config)
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
        main_config = self.config_dir / "downtown.yaml"
        if main_config.exists():
            with open(main_config, encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}
                self.app_config = config_data
                ### Extract nodes_config from downtown.yaml
                self.nodes_config = config_data.get("nodes", {})
                ### Extract backup_storage_config from downtown.yaml
                self.backup_storage_config = config_data.get("backup_storage", {})

        ### Load SSH profiles
        ssh_config = self.config_dir / "ssh_profiles.yaml"
        if ssh_config.exists():
            with open(ssh_config, encoding="utf-8") as f:
                self.ssh_profiles = yaml.safe_load(f) or {}

        ### Load vendor configs
        vendors_dir = self.config_dir / "vendors"
        if vendors_dir.exists():
            for vendor_file in vendors_dir.glob("*.yaml"):
                with open(vendor_file, encoding="utf-8") as f:
                    vendor_config = yaml.safe_load(f) or {}
                    vendor_id = vendor_config.get("vendor", {}).get("id", vendor_file.stem)
                    self.vendors[vendor_id] = vendor_config

        ### Build database URL from backup_storage config
        self.database_url = self._build_database_url()

    def get_ssh_profile(self, profile_name: str) -> dict[str, Any]:
        """Get SSH profile configuration."""
        profiles = self.ssh_profiles.get("profiles", {})
        return profiles.get(profile_name, profiles.get("modern", {}))

    def get_vendor_config(self, vendor_id: str) -> dict[str, Any]:
        """Get vendor-specific configuration."""
        return self.vendors.get(vendor_id, {})

    def _build_database_url(self) -> str:
        """Build database URL from backup_storage configuration.

        Returns:
            SQLAlchemy database URL string
        """
        if not self.backup_storage_config:
            ### Raise error and don't fallback to any defaults - backup storage config is required
            raise ValueError("Backup storage configuration is missing in downtown.yaml")

        db_type = self.backup_storage_config.get("type").lower()

        if db_type == "sqlite":
            path = self.backup_storage_config.get("path", "downtown.sqlite")
            ### If relative path, make it absolute relative to config_dir
            if not Path(path).is_absolute():
                path = self.config_dir / path
            return f"sqlite:///{Path(path).resolve()}"

        elif db_type == "postgresql":
            host = self.backup_storage_config.get("host")
            port = self.backup_storage_config.get("port", 5432)
            database = self.backup_storage_config.get("database", "downtown")
            user = self.backup_storage_config.get("user")
            password = self.backup_storage_config.get("password")

            ### TODO: Switch to more explicit checks?
            if not all([host, port, database, user, password]):
                raise ValueError("Missing required PostgreSQL configuration fields")

        else:
            raise ValueError(f"Unsupported database type: {db_type}")

    def get_device_config(self, group: str, device_name: str) -> dict[str, Any]:
        """
        Resolve device configuration with priority: Node-specific > Group defaults

        Group cannot be overridden - it must be changed in the source.
        Returns a dict with resolved ssh_profile, vendor, and other settings.
        """
        device_config = {}

        ### Step 1: Apply group-level defaults
        groups = self.app_config.get("groups", {})
        if group in groups:
            group_config = groups[group]
            device_config.update({
                "ssh_profile": group_config.get("ssh_profile"),
                "vendor": group_config.get("vendor"),
                "timeout": group_config.get("timeout"),
                "username": group_config.get("username"),
            }) # TODO: Display password in any way (encrypted) or leave it?

        ### Step 2: Apply node-specific overrides
        ### NOTE: Group cannot be overridden here - must be changed in source
        if device_name in self.nodes_config:
            node_config = self.nodes_config[device_name]
            if "ssh_profile" in node_config:
                device_config["ssh_profile"] = node_config["ssh_profile"]
            if "vendor" in node_config:
                device_config["vendor"] = node_config["vendor"]
            if "timeout" in node_config:
                device_config["timeout"] = node_config["timeout"]
            if "username" in node_config:
                device_config["username"] = node_config["username"]
            # TODO: Add ability to override password in node_config if needed

        return device_config

@lru_cache  # Last Recently Used cache to store settings instance
def get_settings() -> Settings:
    """Get settings instance or return cached one."""
    settings = Settings()
    settings.load_yaml_configs()
    return settings
