import httpx

class HTTPService:
    """Service for fetching device configuration over HTTP(S)."""

    ### =============================================================================
    ### HTTPService Class Helper Functions
    ### =============================================================================

    ...

    ### =============================================================================
    ### HTTPService Class PUBLIC Functions
    ### =============================================================================

    ...

    async def get_config(
        self,
        device: DeviceBase,
        *,
        device_config: dict[str, Any] | None = None,
    ) -> tuple[str, str | None]:
        """Get device configuration plus optional metadata via HTTP(S) or local simulator."""

### Singleton instance
http_service = HTTPService()