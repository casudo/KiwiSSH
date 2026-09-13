import httpx
import asyncio
import logging
import re
from typing import Any


from app.core import get_settings
from app.models.device import DeviceBase
from app.services.vendor_service import vendor_service
from app.services.ssh_service import SSHService

logger = logging.getLogger(__name__)

class HTTPService:
    """Service for fetching device configuration over HTTP(S)."""

    def __init__(self) -> None:
        self.settings = get_settings()

    ### =============================================================================
    ### HTTPService Class Helper Functions
    ### =============================================================================

    @staticmethod
    def _render_placeholders(value: Any, context: dict[str, str]) -> Any:
        """Recursively substitute '{{ key }}' placeholders using the given context."""
        if isinstance(value, str):
            ### Matches placeholder tokens like "{{ username }}" (whitespace insensitive)
            return re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}").sub(
                lambda match: context.get(match.group(1), match.group(0)),
                value,
            )
        if isinstance(value, dict):
            return {key: HTTPService._render_placeholders(item, context) for key, item in value.items()}
        if isinstance(value, list):
            return [HTTPService._render_placeholders(item, context) for item in value]
        return value
    @staticmethod
    def _build_request_kwargs(step: dict[str, Any], context: dict[str, str]) -> dict[str, Any]:
        """Build httpx request kwargs (method/url/body/headers/params) from a step."""
        method = str(step.get("method", "GET")).strip().upper() or "GET"
        raw_path = str(step.get("path", "")).strip()
        if not raw_path:
            raise RuntimeError("HTTP step requires a non-empty 'path'")

        path = HTTPService._render_placeholders(raw_path, context)
        headers = HTTPService._render_placeholders(step.get("headers", {}) or {}, context)
        params = HTTPService._render_placeholders(step.get("params", {}) or {}, context)

        kwargs: dict[str, Any] = {
            "method": method,
            "url": path,
            "headers": {str(key): str(val) for key, val in dict(headers).items()},
            "params": {str(key): str(val) for key, val in dict(params).items()},
        }

        ### Request body: exactly one of json / form / body is expected
        if step.get("json") is not None:
            kwargs["json"] = HTTPService._render_placeholders(step.get("json"), context)
        elif step.get("form") is not None:
            form = HTTPService._render_placeholders(step.get("form"), context)
            kwargs["data"] = {str(key): str(val) for key, val in dict(form).items()}
        elif step.get("body") is not None:
            kwargs["content"] = HTTPService._render_placeholders(str(step.get("body")), context)

        return kwargs

    @staticmethod
    def _validate_status(response: httpx.Response, step: dict[str, Any]) -> None:
        """Raise when the response status is not accepted by the step definition."""
        expected = step.get("expected_status")
        if expected is None:
            ### Default: accept any 2xx status code
            if not (200 <= response.status_code < 300):
                raise RuntimeError(f"Unexpected HTTP status {response.status_code}")
            return

        expected_codes = [expected] if isinstance(expected, int) else list(expected)
        if response.status_code not in {int(code) for code in expected_codes}:
            raise RuntimeError(
                f"Unexpected HTTP status {response.status_code} (expected {expected_codes})"
            )
    async def _collect_vendor_config(
        self,
        device: DeviceBase,
        vendor_id: str,
        *,
        scheme: str,
        port: int,
        default_timeout: int,
        verify_ssl: bool,
        context: dict[str, str],
    ) -> tuple[str, str | None]:
        """Fetch and assemble device configuration via vendor-defined HTTP requests."""
        ### Get configured 'http' section for the vendor
        http_config = vendor_service.get_http_config(vendor_id)
        if not http_config:
            raise ValueError(
                f"Vendor '{vendor_id}' has no 'http' backup configuration defined"
            )

        ### Get configured HTTP request steps for the vendor (equivalent to 'ssh.commands' in SSH/Telnet)
        raw_requests = http_config.get("requests")
        request_steps: list[dict[str, Any]]
        if isinstance(raw_requests, dict):
            request_steps = [raw_requests]
        elif isinstance(raw_requests, list):
            request_steps = [step for step in raw_requests if isinstance(step, dict)]
        else:
            request_steps = []
        if not request_steps:
            raise ValueError(f"Vendor '{vendor_id}' has no http.requests configured")

        ### HTTP backups store each request's full response; only vendor processing is applied
        processing_rules = vendor_service.get_processing_rules(vendor_id)

        base_url = f"{scheme}://{context['host']}:{port}"
        base_headers = {
            str(key): str(val)
            for key, val in dict(self._render_placeholders(http_config.get("headers", {}) or {}, context)).items()
        }

        ### Basic auth is applied at the client level
        auth_config = http_config.get("auth") or {}
        auth_type = str(auth_config.get("type", "none")).strip().lower()
        client_auth: httpx.BasicAuth | None = None
        if auth_type == "basic":
            client_auth = httpx.BasicAuth(context.get("username", ""), context.get("password", ""))

        captured_output: list[dict[str, Any]] = []
        async with httpx.AsyncClient(
            base_url=base_url,
            verify=verify_ssl,
            timeout=default_timeout,
            headers=base_headers,
            auth=client_auth,
            follow_redirects=True,
        ) as client:

            ### Config requests whose responses form the stored configuration
            for step in request_steps:
                request_kwargs = self._build_request_kwargs(step, context)
                label = str(step.get("label") or f"{request_kwargs['method']} {request_kwargs['url']}").strip()
                logger.debug("HTTP backup request for '%s': %s", device.device_name, label)

                ### Make the HTTP request
                response = await client.request(timeout=default_timeout, **request_kwargs)
                self._validate_status(response, step)

                ### HTTP backups always store the full response body
                output = response.text
                if output and output.strip():
                    captured_output.append({
                        "command": label,
                        "output": output,
                        "show_command_in_config": bool(step.get("show_command_in_config", False)),
                    })

        ### Assemble config body from every request's full response (mirrors SSH/Telnet body)
        config_outputs: list[str] = []
        for chunk in captured_output:
            output = str(chunk.get("output", "")).strip()
            if not output:
                continue
            if bool(chunk.get("show_command_in_config", False)):
                label = str(chunk.get("command", "")).strip()
                if label:
                    output = f"### Source: {label}\n{output}"
            config_outputs.append(output)

        ### Build and check the raw configuration output
        raw_config = "\n\n".join(output for output in config_outputs if output)
        if not raw_config:
            raise RuntimeError("HTTP backup requests completed but returned empty config output")

        ### Reuse the shared vendor processing pipeline (strip_patterns, redaction, etc.)
        processed_config = SSHService._apply_processing_rules(raw_config, processing_rules)

        ### HTTP backups have no separate metadata section
        return processed_config, None
    ) -> tuple[str, str | None]:

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
        verify_ssl = bool(device_config.get("verify_ssl", True))
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
                config, metadata_output = await self._collect_vendor_config(
                    device=device,
                    vendor_id=vendor_id,
                    scheme=protocol,
                    port=device_port,
                    default_timeout=timeout_seconds,
                    verify_ssl=verify_ssl,
                    context=context,
                )
                if attempt > 1:
                    logger.warning(
                        "Config fetch for device '%s' succeeded on retry attempt %d/%d",
                        device.device_name,
                        attempt,
                        max_attempts,
                    )
                return config, metadata_output
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
