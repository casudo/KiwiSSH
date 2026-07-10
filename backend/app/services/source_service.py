"""Device source parsing service."""

import csv
from pathlib import Path
import re
import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError

from app.core import get_settings
from app.models.device import DeviceBase


class SourceService:
    """Service for loading devices from various sources."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._devices_cache: dict[str, DeviceBase] = {}
        self._loaded = False

    def _get_csv_source_path(self) -> Path:
        """Resolve CSV source path from sources.file string."""

        default_config_path = "/config/sources/devices.csv"

        configured_path = self.settings.sources.file if self.settings.sources else None
        if not configured_path:
            configured_path = default_config_path

        candidate = Path(configured_path)
        return candidate.resolve()

    def _cache_device_from_row(self, row: dict, row_num: int | str) -> None:
        """Build and cache a device from a normalized source row."""

        group = str(row.get("group", "")).strip()
        device_name = str(row.get("device_name", "")).strip()

        if not group:
            raise ValueError(f"Row {row_num}: 'group' column is required")
        if group not in self.settings.groups:
            raise ValueError(
                f"Row {row_num} (device '{device_name}'): Group '{group}' not found in kiwissh.yaml. "
                f"Available groups: {', '.join(self.settings.groups.keys())}"
            )

        device_config = self.settings.get_device_config(group, device_name)

        resolved_ssh_profile = str(device_config.get("ssh_profile") or "").strip()
        if not resolved_ssh_profile and str(device_config.get("protocol")) == "telnet":
            resolved_ssh_profile = "telnet"

        enabled_raw = row.get("enabled", True)
        if isinstance(enabled_raw, bool):
            enabled = enabled_raw
        else:
            enabled = str(enabled_raw).strip().lower() == "true"

        device = DeviceBase(
            group=group,
            device_name=device_name,
            ip_address=str(row.get("ip_address", "")).strip(),
            vendor=device_config["vendor"],
            ssh_profile=resolved_ssh_profile,
            protocol=str(device_config.get("protocol")).strip().lower(),
            port=int(device_config.get("port") or 22),
            enabled=enabled,
        )
        self._devices_cache[device.device_name] = device

    @staticmethod
    def _validate_table_name(table_name: str) -> str:
        """Validate and return PostgreSQL table name from configuration."""

        normalized = table_name.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", normalized):
            raise ValueError(
                "Invalid sources.postgres.table value. Use only letters, numbers, and underscore."
            )
        return normalized

    async def load_devices_from_csv(self) -> list[DeviceBase]:
        """Load devices from CSV file.

        CSV columns required: group, device_name, ip_address, enabled
        Vendor and ssh_profile are resolved from kiwissh.yaml configuration.
        Priority: App defaults < Group defaults < Node-specific overrides
        """
        csv_path = self._get_csv_source_path()

        if not csv_path.exists():
            return []

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_num, row in enumerate(reader, start=2):  # Start at 2 to account for header
                self._cache_device_from_row(row, row_num)

        self._loaded = True
        return list(self._devices_cache.values())

    async def load_devices_from_postgres(self) -> list[DeviceBase]:
        """Load devices from a PostgreSQL source table."""
        src = self.settings.sources.postgres
        source_url = self.settings.get_source_postgres_url()

        table_name = self._validate_table_name(src.table)
        quoted_table_name = f'"{table_name}"'

        query = text(
            f"""
            SELECT
                "group" AS "group",
                device_name,
                ip_address,
                enabled
            FROM {quoted_table_name}
            """
        )

        engine = create_engine(
            source_url,
            future=True,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 5},
        )
        try:
            with engine.connect() as conn:
                rows = conn.execute(query).mappings().all()
        except OperationalError as e:
            details = str(getattr(e, "orig", e)).lower()
            if "password authentication failed" in details or "authentication failed" in details:
                raise ValueError(
                    "Unable to connect to sources.postgres: invalid credentials. "
                    "Verify sources.postgres.username and sources.postgres.password."
                ) from e
            raise ValueError(
                "Unable to connect to sources.postgres. Verify host, port, database, username, and password."
            ) from e
        except ProgrammingError as e:
            details = str(getattr(e, "orig", e)).lower()
            if "does not exist" in details and "column" in details:
                raise ValueError(
                    f"Configured source table '{table_name}' is missing one or more required columns: "
                    "group, device_name, ip_address, enabled."
                ) from e
            if "does not exist" in details:
                raise ValueError(
                    f"Configured source table '{table_name}' was not found in the PostgreSQL source database."
                ) from e
            raise ValueError(
                f"Invalid query against configured source table '{table_name}'. "
                "Ensure required columns exist: group, device_name, ip_address, enabled."
            ) from e
        except SQLAlchemyError as e:
            raise ValueError(
                "Failed to load devices from sources.postgres due to a database error."
            ) from e
        finally:
            engine.dispose()

        for index, row in enumerate(rows, start=1):
            self._cache_device_from_row(dict(row), f"db#{index}")

        self._loaded = True
        return list(self._devices_cache.values())

    def _map_http_item(self, item: dict, field_map: dict[str, str], default_group: str | None) -> dict:
        """Translate a raw HTTP response item into a canonical source row."""
        ### field_map maps canonical KiwiSSH field -> JSON field name in the response
        row: dict = {}
        for canonical, json_field in field_map.items():
            if json_field in item and item[json_field] is not None:
                row[canonical] = item[json_field]

        ### Apply the fallback group when none was provided by the response item
        if not str(row.get("group", "")).strip() and default_group:
            row["group"] = default_group

        ### Default to enabled when the source doesn't carry an 'enabled' field
        if "enabled" not in row:
            row["enabled"] = True

        return row

    @staticmethod
    def _extract_http_items(payload: object, items_key: str | None) -> list:
        """Extract the device list from an HTTP JSON payload."""
        ### Return JSON arrays as-is
        if isinstance(payload, list):
            return payload
        
        ### If response is a dict, search for the items_key key and get the item list
        if isinstance(payload, dict):
            ### Explicitly configured key takes precedence
            if items_key:
                nested = payload.get(items_key)
                if not isinstance(nested, list):
                    raise ValueError(
                        f"sources.http response has no list under configured items_key '{items_key}'"
                    )
                return nested

            ### TODO: Default item keys if dict and no items_key is configured? e.g. devices, items, data, list

        raise ValueError(
            "sources.http response must be a JSON array of devices or an object containing one. "
            "Set sources.http.items_key if the list is nested under a specific key."
        )

    async def load_devices_from_http(self) -> list[DeviceBase]:
        """Load devices from a generic HTTP source."""
        src = self.settings.sources.http

        ### Step 1: Fetch API endpoint and parse JSON response
        try:
            ### Build HTTP client from config
            async with httpx.AsyncClient(
                headers=src.headers,
                verify=src.verify_tls,
                timeout=src.timeout,
                follow_redirects=True,
            ) as client:
                response = await client.get(src.url)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as e:
            raise ValueError(
                f"sources.http request to '{src.url}' failed with HTTP {e.response.status_code}. "
                "Verify the URL and authentication headers (e.g. X-Auth-Token)."
            ) from e
        except httpx.HTTPError as e:
            raise ValueError(
                f"Unable to reach sources.http endpoint '{src.url}': {e}"
            ) from e
        except ValueError as e:
            ### Raised by response.json() on invalid JSON payloads
            raise ValueError(
                f"sources.http endpoint '{src.url}' did not return valid JSON."
            ) from e

        ### Step 2: Extract device list from JSON payload
        items = self._extract_http_items(payload, src.items_key)

        ### Step 3: Map each item to a canonical source row and cache devices
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ValueError(
                    f"sources.http item #{index} is not a JSON object and cannot be mapped."
                )
            row = self._map_http_item(item, src.map, src.default_group)
            self._cache_device_from_row(row, f"http#{index}")

        self._loaded = True
        return list(self._devices_cache.values())

    async def load_devices(self) -> list[DeviceBase]:
        """Load devices from configured source."""

        if self.settings.sources.postgres:
            return await self.load_devices_from_postgres()
        elif self.settings.sources.http:
            return await self.load_devices_from_http()
        elif self.settings.sources.file:
            return await self.load_devices_from_csv()

    async def get_device(self, device_name: str) -> DeviceBase | None:
        """Get a single device by name."""
        if not self._loaded:
            await self.load_devices()
        return self._devices_cache.get(device_name)

    async def get_devices_by_group(self, group: str) -> list[DeviceBase]:
        """Get all devices in a group."""
        if not self._loaded:
            await self.load_devices()
        return [d for d in self._devices_cache.values() if d.group == group]

    async def get_all_devices(self) -> list[DeviceBase]:
        """Get all devices."""
        if not self._loaded:
            await self.load_devices()
        return list(self._devices_cache.values())

    async def get_enabled_devices(self) -> list[DeviceBase]:
        """Get all enabled devices."""
        if not self._loaded:
            await self.load_devices()
        return [d for d in self._devices_cache.values() if d.enabled]

    async def get_groups(self) -> list[str]:
        """Get list of all groups."""
        if not self._loaded:
            await self.load_devices()
        return list(set(d.group for d in self._devices_cache.values()))

    def invalidate_cache(self) -> None:
        """Clear the device cache to force reload."""
        self.settings = get_settings()
        self._devices_cache.clear()
        self._loaded = False


### Singleton instance
source_service = SourceService()
