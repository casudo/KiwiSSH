"""Vendor configuration service.

This service loads and provides access to vendor-specific configuration
files that define how to backup different types of network devices.
"""

from typing import Any

from app.core import get_settings


class VendorService:
    """Service for loading and accessing vendor configurations."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def get_vendor(self, vendor_id: str) -> dict[str, Any]:
        """
        Get vendor configuration by ID.

        Args:
            vendor_id: Vendor identifier (e.g., 'cisco_ios')

        Returns:
            Vendor configuration dictionary
        """
        return self.settings.get_vendor_config(vendor_id)

    def get_backup_commands(self, vendor_id: str) -> dict[str, list[dict[str, Any]]]:
        """
        Get backup commands for a vendor.

        Args:
            vendor_id: Vendor identifier

        Returns:
            Dictionary with pre_backup, backup, and post_backup command lists
        """
        vendor = self.get_vendor(vendor_id)
        if not vendor:
            raise ValueError(f"Unknown vendor '{vendor_id}'")

        commands = vendor.get("commands", {})

        return {
            "pre_backup": commands.get("pre_backup", []),
            "backup": commands.get("backup", []),
            "post_backup": commands.get("post_backup", []),
        }

    def get_session_parameters(self, vendor_id: str) -> dict[str, Any]:
        """
        Get session parameters for a vendor.

        Args:
            vendor_id: Vendor identifier

        Returns:
            Session parameter dictionary
        """
        vendor = self.get_vendor(vendor_id)
        if not vendor:
            raise ValueError(f"Unknown vendor '{vendor_id}'")

        return vendor.get("session", {})
    
    def get_processing_rules(self, vendor_id: str) -> dict[str, Any]:
        """
        Get configuration processing rules for a vendor.

        Args:
            vendor_id: Vendor identifier

        Returns:
            Dictionary of processing rules
        """
        vendor = self.get_vendor(vendor_id)
        if not vendor:
            raise ValueError(f"Unknown vendor '{vendor_id}'")

        return vendor.get("processing", {})

    def list_vendors(self) -> list[dict[str, str]]:
        """
        List all available vendors.

        Returns:
            List of vendor info dictionaries with id, name, description
        """
        vendors = []
        for vendor_id, config in self.settings.vendors.items():
            vendor_info = config.get("vendor", {})
            vendors.append({
                "id": vendor_id,
                "name": vendor_info.get("name", "<Not_set>"),
                "description": vendor_info.get("description", "<Not_set>"),
            })
        return vendors


### Singleton instance
vendor_service = VendorService()
