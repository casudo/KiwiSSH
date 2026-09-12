import httpx
import asyncio
import logging
from typing import Any
from app.core import get_settings
from app.models.device import DeviceBase
logger = logging.getLogger(__name__)

class HTTPService:
    """Service for fetching device configuration over HTTP(S)."""

    def __init__(self) -> None:
        self.settings = get_settings()

    ### =============================================================================
    ### HTTPService Class Helper Functions
    ### =============================================================================

    ...

    ### =============================================================================
    ### HTTPService Class PUBLIC Functions
    ### =============================================================================

    async def get_config(
        self,
        device: DeviceBase,
        *,
        device_config: dict[str, Any] | None = None,
    ) -> tuple[str, str | None]:
        """Get device configuration plus optional metadata via HTTP(S) or local simulator."""
        device_config = device_config or self.settings.get_device_config(device.group, device.device_name)

        protocol = str(device_config.get("protocol") or "").strip().lower()
        if protocol not in {"http", "https"}:
            raise ValueError(
                f"Device '{device.device_name}' in group '{device.group}' requires an HTTP(S) protocol for http_service.py"
            )

        ### Filter for required HTTP(S) config values
        timeout_seconds = int(device_config["timeout"])
        retry_count = int(device_config["retry"])
        vendor_id = str(device_config["vendor"]).strip()
        default_port = 443 if protocol == "https" else 80
        device_port = int(device_config.get("port") or default_port)
        device_username = str(device_config.get("username") or "").strip()
        device_password = str(device_config.get("password") or "").strip()

        max_attempts = retry_count + 1

        ### Try to fetch config from device, applying retries on failure
        last_exception: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            context: dict[str, str] = {
                "host": str(device.ip_address),
                "username": device_username,
                "password": device_password,
            }
            try:
                ...
            except httpx.TimeoutException as ex:
                last_exception = TimeoutError(
                    f"HTTP config fetch timed out after {timeout_seconds}s "
                    f"(attempt {attempt}/{max_attempts})"
                )
                logger.warning(
                    "Config fetch timeout for device '%s' on attempt %d/%d",
                    device.device_name,
                    attempt,
                    max_attempts,
                )
                logger.debug("Timeout details: %s", ex)
            except Exception as ex:
                last_exception = ex
                logger.warning(
                    "Config fetch failed for device '%s' on attempt %d/%d: %s",
                    device.device_name,
                    attempt,
                    max_attempts,
                    ex,
                )

            ### Wait 0.25sec and try again if there are remaining attempts
            if attempt < max_attempts:
                await asyncio.sleep(0.25)

        if last_exception is not None:
            raise last_exception
        raise RuntimeError("HTTP config fetch failed without a captured exception!!")


### Singleton instance
http_service = HTTPService()
