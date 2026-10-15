"""Device source parsing service."""

import asyncio
import csv
import logging
from pathlib import Path
import re
import httpx
import yaml
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import NoSuchTableError, OperationalError, ProgrammingError, SQLAlchemyError

from app.core import Settings, get_settings
from app.models.device import DeviceBase
from app.core.config import NodeConfig, SOURCE_OVERRIDE_FIELDS

logger = logging.getLogger(__name__)

### A source row paired with a label used in error messages (e.g. CSV line number or "http#3")
## The row is normally a dict; anything else (e.g. a non-object item of an HTTP source) is reported as invalid
SourceRow = tuple[object, int | str]


class SourceService:
    """Service for loading devices from various sources."""

    def __init__(self) -> None:
        self._devices_cache: dict[str, DeviceBase] = {}
        self._loaded = False
        self._load_lock: asyncio.Lock | None = None
        ### Rows of the last load that were skipped because they were invalid
        self._skipped_rows: list[dict[str, str]] = []

    @property
    def settings(self) -> Settings:
        """Current settings, resolved on every access so a settings reload never leaves a stale copy behind."""
        return get_settings()

    def _get_load_lock(self) -> asyncio.Lock:
        """Get lock that serializes inventory loads and reloads."""
        if self._load_lock is None:
            self._load_lock = asyncio.Lock()
        return self._load_lock

    ### =============================================================================
    ### SourceService Class Helper Functions
    ### =============================================================================


    def _parse_source_overrides(self, row: dict) -> NodeConfig | None:
        """Validate per-device overrides parsed from a source row."""
        overrides: dict = {}
        for field in SOURCE_OVERRIDE_FIELDS:
            if field not in row:
                continue
            value = row[field]
            if value is None:
                continue
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    continue
            overrides[field] = value
        
        if not overrides:
            return None
        try:
            return NodeConfig(**overrides)
        except ValidationError as exc:
            raise ValueError(f"invalid override value(s): {self._format_validation_error(exc)}") from exc

    @staticmethod
    def _format_validation_error(exc: ValidationError) -> str:
        """Turn a pydantic error into a short one-line message such as 'ip_address: Value error, ...'."""
        return "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" if error["loc"] else error["msg"]
            for error in exc.errors()
        )

    def _build_device_from_row(self, row: object) -> tuple[DeviceBase, NodeConfig | None]:
        """Build a device and its optional source overrides from a normalized source row.

        Raises ValueError (or another exception) when the row is invalid.
        """
        if not isinstance(row, dict):
            raise ValueError("entry is not an object and cannot be mapped to a device")

        group = str(row.get("group", "")).strip()
        device_name = str(row.get("device_name", "")).strip()

        if not group:
            raise ValueError("'group' column is required")
        if group not in self.settings.groups:
            raise ValueError(
                f"Group '{group}' not found in kiwissh.yaml. "
                f"Available groups: {', '.join(self.settings.groups.keys())}"
            )

        ### Resolve the config with this row's overrides so they take effect
        node_override = self._parse_source_overrides(row)
        device_config = self.settings.get_device_config(
            group,
            device_name,
            source_overrides={device_name: node_override} if node_override is not None else {},
        )

        resolved_protocol = str(device_config.get("protocol")).strip().lower()
        resolved_ssh_profile = str(device_config.get("ssh_profile") or "").strip()
        ### DeviceBase requires a non-empty ssh_profile; non-SSH protocols use the
        ## protocol name as a placeholder since they dont rely on an SSH profile
        if not resolved_ssh_profile and resolved_protocol != "ssh":
            resolved_ssh_profile = resolved_protocol

        enabled_raw = row.get("enabled", True)
        if isinstance(enabled_raw, bool):
            enabled = enabled_raw
        else:
            enabled = str(enabled_raw).strip().lower() == "true"

        try:
            device = DeviceBase(
                group=group,
                device_name=device_name,
                ip_address=str(row.get("ip_address", "")).strip(),
                vendor=device_config["vendor"],
                ssh_profile=resolved_ssh_profile,
                protocol=resolved_protocol,
                port=int(device_config.get("port") or 22),
                enabled=enabled,
            )
        except ValidationError as exc:
            raise ValueError(self._format_validation_error(exc)) from exc
        return device, node_override

    ### =============================================================================
    ### CSV Source Functions
    ### =============================================================================

    def _get_csv_source_path(self) -> Path:
        """Resolve CSV source path from sources.file string."""

        default_config_path = "/config/sources/devices.csv"

        configured_path = self.settings.sources.file if self.settings.sources else None
        if not configured_path:
            configured_path = default_config_path

        candidate = Path(configured_path)
        return candidate.resolve()
    
    def _read_csv_rows(self) -> list[SourceRow]:
        """Read device rows from CSV file (blocking - intended to run via asyncio.to_thread).

        CSV columns required: group, device_name, ip_address, enabled
        Vendor and ssh_profile are resolved from kiwissh.yaml configuration.
        Priority: App defaults < Group defaults < Node-specific overrides
        """
        csv_path = self._get_csv_source_path()

        if not csv_path.exists():
            return []

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [(row, row_num) for row_num, row in enumerate(reader, start=2)]  # Start at 2 to account for header
    
    ### =============================================================================
    ### Ansible Source Functions
    ### =============================================================================

    def _get_ansible_source_path(self) -> Path:
        """Resolve Ansible inventory source path from sources.ansible string."""

        default_config_path = "/config/sources/inventory.yaml"

        configured_path = self.settings.sources.ansible if self.settings.sources else None
        if not configured_path:
            configured_path = default_config_path

        candidate = Path(configured_path)
        return candidate.resolve()
    
    @staticmethod
    def _walk_inventory_group(group_name: str, group_data: object, rows: list[dict]) -> None:
        """Recursively collect device rows from an Ansible inventory group node.

        A device's group is the immediate Ansible group under which it is listed in 'hosts'.
        The connection IP is taken from 'ansible_host'.
        """
        if not isinstance(group_data, dict):
            return

        hosts = group_data.get("hosts") or {}
        if isinstance(hosts, dict):
            ### Scan through all hosts in the group
            for host_name, host_vars in hosts.items():
                host_vars = host_vars if isinstance(host_vars, dict) else {}
                ip_address = str(host_vars.get("ansible_host")).strip()
                ### Map Ansible inventory hosts to canonical KiwiSSH device rows
                device_row = {
                    "group": group_name,
                    "device_name": str(host_name).strip(),
                    "ip_address": ip_address,
                    "enabled": host_vars.get("enabled", True),
                }
                ### Carry optional per-device overrides declared as host vars
                for field in SOURCE_OVERRIDE_FIELDS:
                    if field in host_vars and host_vars[field] is not None:
                        device_row[field] = host_vars[field]
                rows.append(device_row)

        ### Handle children groups recursively, if present
        children = group_data.get("children") or {}
        if isinstance(children, dict):
            for child_name, child_data in children.items():
                SourceService._walk_inventory_group(str(child_name), child_data, rows)

    def _parse_ansible_inventory(self, data: dict) -> list[dict]:
        """Flatten a nested Ansible inventory mapping into normalized device rows."""
        rows: list[dict] = []
        for group_name, group_data in data.items():
            self._walk_inventory_group(str(group_name), group_data, rows)
        return rows

    def _read_ansible_rows(self) -> list[SourceRow]:
        """Read device rows from an Ansible inventory YAML file (blocking - intended to run via asyncio.to_thread).

        Ansible groups (under 'all.children') map to KiwiSSH groups and must exist in kiwissh.yaml.
        Each host under a groups 'hosts' becomes a device, using 'ansible_host' as the IP.
        """
        inventory_path = self._get_ansible_source_path()

        if not inventory_path.exists():
            return []

        with open(inventory_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        if not isinstance(data, dict):
            raise ValueError(
                f"Invalid Ansible inventory at '{inventory_path}': expected a YAML mapping at the top level"
            )

        ### Parse Ansible inventory into device rows
        rows = self._parse_ansible_inventory(data)
        return [(row, f"ansible#{index}") for index, row in enumerate(rows, start=1)]
    
    ### =============================================================================
    ### PostgreSQL Source Functions
    ### =============================================================================

    @staticmethod
    def _validate_table_name(table_name: str) -> str:
        """Validate and return PostgreSQL table name from configuration."""

        normalized = table_name.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", normalized):
            raise ValueError(
                "Invalid sources.postgres.table value. Use only letters, numbers, and underscore."
            )
        return normalized

    def _read_postgres_rows(self) -> list[SourceRow]:
        """Read device rows from a PostgreSQL source table (blocking - intended to run via asyncio.to_thread)."""
        src = self.settings.sources.postgres
        source_url = self.settings.get_source_postgres_url()

        table_name = self._validate_table_name(src.table)
        quoted_table_name = f'"{table_name}"'

        engine = create_engine(
            source_url,
            future=True,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 5},
        )
        try:
            with engine.connect() as conn:
                ### Include optional per-device override columns ONLY when they exist in the table!
                ## Required columns: "group", "device_name", "ip_address", "enabled"
                available_cols = {col["name"] for col in inspect(conn).get_columns(table_name)}
                override_cols = [f for f in SOURCE_OVERRIDE_FIELDS if f in available_cols] # find optional override columns
                select_extra = "".join(f',\n                "{col}"' for col in override_cols) # apply optional override columns to the SELECT statement

                query = text(
                    f"""
                    SELECT
                        "group" AS "group",
                        device_name,
                        ip_address,
                        enabled{select_extra}
                    FROM {quoted_table_name}
                    """
                )
                rows = conn.execute(query).mappings().all()
        except NoSuchTableError as e:
            raise ValueError(
                f"Configured source table '{table_name}' was not found in the PostgreSQL source database."
            ) from e
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

        return [(dict(row), f"db#{index}") for index, row in enumerate(rows, start=1)]

    ### =============================================================================
    ### HTTP Source Functions
    ### =============================================================================

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

    async def _read_http_rows(self) -> list[SourceRow]:
        """Read device rows from a generic HTTP source."""
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

        ### Step 3: Map each item to a canonical source row
        rows: list[SourceRow] = []
        for index, item in enumerate(items, start=1):
            ### Non-object items are passed on as they are and reported as invalid rows when loading
            row = self._map_http_item(item, src.map, src.default_group) if isinstance(item, dict) else item
            rows.append((row, f"http#{index}"))
        return rows

    ### =============================================================================
    ### Inventory Loading
    ### =============================================================================

    async def _read_source_rows(self) -> list[SourceRow]:
        """Read raw device rows from the configured source without blocking the event loop."""
        sources = self.settings.sources
        if sources is None:
            return []

        if sources.postgres:
            return await asyncio.to_thread(self._read_postgres_rows)
        elif sources.http:
            return await self._read_http_rows()
        elif sources.ansible:
            return await asyncio.to_thread(self._read_ansible_rows)
        elif sources.file:
            return await asyncio.to_thread(self._read_csv_rows)
        return []

    async def _load_inventory_locked(self) -> list[DeviceBase]:
        """Load the inventory into new containers and swap them in only once everything is valid.

        Caller must hold the load lock.
        """
        rows = await self._read_source_rows()

        devices: dict[str, DeviceBase] = {}
        source_overrides: dict[str, NodeConfig] = {}
        device_rows: dict[str, int | str] = {}
        skipped_rows: list[dict[str, str]] = []
        for row, row_num in rows:
            device_name = str(row.get("device_name", "")).strip() if isinstance(row, dict) else ""

            ### One invalid row must not take down the whole inventory: skip and report it instead
            try:
                if device_name in device_rows:
                    raise ValueError(f"duplicate device_name, already defined in row {device_rows[device_name]}")
                device, node_override = self._build_device_from_row(row)
            except Exception as ex:
                logger.warning("Skipping invalid source row %s (device '%s'): %s", row_num, device_name, ex)
                skipped_rows.append({"row": str(row_num), "device_name": device_name, "error": str(ex)})
                continue

            devices[device.device_name] = device
            device_rows[device.device_name] = row_num
            if node_override is not None:
                source_overrides[device.device_name] = node_override

        if skipped_rows:
            logger.warning(
                "Loaded %d device(s) from source, skipped %d invalid row(s)",
                len(devices),
                len(skipped_rows),
            )

        ### Swap devices and their source overrides together
        self.settings.replace_source_overrides(source_overrides)
        self._devices_cache = devices
        self._skipped_rows = skipped_rows
        self._loaded = True
        return list(devices.values())

    async def _ensure_loaded(self) -> None:
        """Load the inventory on first use; concurrent callers wait for the same load."""
        if self._loaded:
            return
        async with self._get_load_lock():
            if not self._loaded:
                await self._load_inventory_locked()

    ### =============================================================================
    ### SourceService Class PUBLIC Functions
    ### =============================================================================

    async def load_devices(self) -> list[DeviceBase]:
        """(Re)load devices from configured source.

        If loading fails, the previous inventory stays in place and the error is raised.
        """
        async with self._get_load_lock():
            return await self._load_inventory_locked()

    @property
    def skipped_rows(self) -> list[dict[str, str]]:
        """Rows of the last load that were skipped as invalid, each with 'row', 'device_name' and 'error'."""
        return list(self._skipped_rows)

    async def get_device(self, device_name: str) -> DeviceBase | None:
        """Get a single device by name."""
        await self._ensure_loaded()
        return self._devices_cache.get(device_name)

    async def get_devices_by_group(self, group: str) -> list[DeviceBase]:
        """Get all devices in a group."""
        await self._ensure_loaded()
        return [d for d in self._devices_cache.values() if d.group == group]

    async def get_all_devices(self) -> list[DeviceBase]:
        """Get all devices."""
        await self._ensure_loaded()
        return list(self._devices_cache.values())

    async def get_enabled_devices(self) -> list[DeviceBase]:
        """Get all enabled devices."""
        await self._ensure_loaded()
        return [d for d in self._devices_cache.values() if d.enabled]

    async def get_groups(self) -> list[str]:
        """Get list of all groups."""
        await self._ensure_loaded()
        return list(set(d.group for d in self._devices_cache.values()))

    def invalidate_cache(self) -> None:
        """Clear the device cache to force reload."""
        self.settings.clear_source_overrides()
        self._devices_cache.clear()
        self._loaded = False


### Singleton instance
source_service = SourceService()
