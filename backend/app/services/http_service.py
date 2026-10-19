import httpx
import asyncio
import logging
import re
from typing import Any


from app.core import Settings, get_settings
from app.models.device import DeviceBase
from app.services.vendor_service import vendor_service
from app.services.local_ssh_simulator import local_ssh_simulator
from app.services.protocol_common import apply_processing_rules, fetch_with_retries

logger = logging.getLogger(__name__)

class HTTPService:
    """Service for fetching device configuration over HTTP(S)."""

    @property
    def settings(self) -> Settings:
        """Current settings, resolved on every access so a settings reload never leaves a stale copy behind."""
        return get_settings()

    ### =============================================================================
    ### HTTPService Class Helper Functions
    ### =============================================================================

    @staticmethod
    def _render_placeholders(value: Any, context: dict[str, Any]) -> Any:
        """Recursively substitute '{{ key }}' placeholders using the given context."""
        if isinstance(value, str):
            ### Matches placeholder tokens like "{{ username }}" (whitespace insensitive)
            return re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}").sub(
                lambda match: str(context.get(match.group(1), match.group(0))),
                value,
            )
        if isinstance(value, dict):
            return {key: HTTPService._render_placeholders(item, context) for key, item in value.items()}
        if isinstance(value, list):
            return [HTTPService._render_placeholders(item, context) for item in value]
        return value

    @staticmethod
    def _build_auth(auth_config: dict[str, Any] | None, context: dict[str, Any]) -> httpx.Auth | None:
        """Build the httpx auth for an 'auth' mapping; username/password default to the device credentials."""
        auth_config = auth_config or {}
        auth_type = str(auth_config.get("type", "none")).strip().lower()
        if auth_type == "none":
            return None

        ### username/password may use placeholders, e.g. an extracted API key
        username = HTTPService._render_placeholders(str(auth_config.get("username", "{{ username }}")), context)
        password = HTTPService._render_placeholders(str(auth_config.get("password", "{{ password }}")), context)
        
        if auth_type == "basic":
            return httpx.BasicAuth(username, password)
        if auth_type == "digest":
            return httpx.DigestAuth(username, password)
        raise ValueError(f"Unknown HTTP auth type '{auth_type}' (expected none, basic or digest)")

    @staticmethod
    def _format_url_host(host: str) -> str:
        """Return the host as it has to appear in a URL.

        IPv6 addresses must be wrapped in brackets, otherwise their colons are read as the port separator
        (e.g. https://[2001:db8::1]:443). A zone ID like 'fe80::1%eth0' needs its '%' percent-encoded.
        """
        if ":" in host and not host.startswith("["):
            return f"[{host.replace('%', '%25')}]"
        return host

    @staticmethod
    def _build_request_kwargs(step: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
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
        }

        ### Only pass 'params' when set: httpx drops a query written in the path (e.g. a scraped link) whenever params are passed
        if params:
            kwargs["params"] = {str(key): str(val) for key, val in dict(params).items()}

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
        context: dict[str, Any],
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

        ### Apply processing rules to the HTTP response
        processing_rules = vendor_service.get_processing_rules(vendor_id)

        base_url = f"{scheme}://{self._format_url_host(context['host'])}:{port}"
        base_headers = {
            str(key): str(val)
            for key, val in dict(self._render_placeholders(http_config.get("headers", {}) or {}, context)).items()
        }

        ### Default auth is applied at the client level, a request can override it with its own 'auth'
        client_auth = self._build_auth(http_config.get("auth"), context)

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
        processed_config = apply_processing_rules(raw_config, processing_rules)

        ### HTTP backups have no separate metadata section
        return processed_config, None

    async def _collect_local_vendor_config(
        self,
        device: DeviceBase,
        vendor_id: str,
        timeout_seconds: int,
    ) -> tuple[str, str | None]:
        """Collect config in local test mode while reusing vendor processing rules."""
        ### Keep vendor validation parity with the real HTTP path
        http_config = vendor_service.get_http_config(vendor_id)
        if not http_config or not http_config.get("requests"):
            raise ValueError(f"Vendor '{vendor_id}' has no http.requests configured")

        raw_config = await asyncio.wait_for(
            local_ssh_simulator.get_config(device),
            timeout=timeout_seconds,
        )
        if not raw_config.strip():
            raise RuntimeError("Local simulator returned empty config output")

        processing_rules = vendor_service.get_processing_rules(vendor_id)
        return apply_processing_rules(raw_config, processing_rules), None

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

        ### Use the local simulator if test mode is enabled
        if self.settings.local_test_mode:
            return await self._collect_local_vendor_config(
                device=device,
                vendor_id=vendor_id,
                timeout_seconds=timeout_seconds,
            )

        async def fetch_once() -> tuple[str, str | None]:
            context: dict[str, str] = {
                "host": str(device.ip_address),
                "username": device_username,
                "password": device_password,
            }
            return await self._collect_vendor_config(
                device=device,
                vendor_id=vendor_id,
                scheme=protocol,
                port=device_port,
                default_timeout=timeout_seconds,
                verify_ssl=verify_ssl,
                context=context,
            )

        ### Try to fetch config from device, applying retries on failure
        return await fetch_with_retries(
            device,
            fetch_once,
            max_attempts=retry_count + 1,
            timeout_seconds=timeout_seconds,
            protocol_label="HTTP",
            timeout_exceptions=(httpx.TimeoutException,),
        )

### Singleton instance
http_service = HTTPService()
