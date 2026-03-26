"""Project Downtown application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment and config files."""

    ### TODO: Make some settings configurable via .env
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

    ### Loaded from YAML files
    app_config: dict[str, Any] = Field(default_factory=dict)
    ssh_profiles: dict[str, Any] = Field(default_factory=dict)
    vendors: dict[str, dict[str, Any]] = Field(default_factory=dict)

    def load_yaml_configs(self) -> None:
        """Load YAML configuration files."""
        ### Load main config
        main_config = self.config_dir / "downtown.yaml"
        if main_config.exists():
            with open(main_config, encoding="utf-8") as f:
                self.app_config = yaml.safe_load(f) or {}

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


    def get_ssh_profile(self, profile_name: str) -> dict[str, Any]:
        """Get SSH profile configuration."""
        profiles = self.ssh_profiles.get("profiles", {})
        return profiles.get(profile_name, profiles.get("modern", {}))

    def get_vendor_config(self, vendor_id: str) -> dict[str, Any]:
        """Get vendor configuration."""
        return self.vendors.get(vendor_id, {})


@lru_cache # Last Recently Used cache to store settings instance
def get_settings() -> Settings:
    """Get settings instance or return cached one."""
    settings = Settings()
    settings.load_yaml_configs()
    return settings
