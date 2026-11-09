"""Container healthcheck.

Asks the readiness endpoint whether the backend is ready and exits with 0 (healthy) or 1 (unhealthy).
Used by the HEALTHCHECK instruction in Dockerfile_backend.

Only the `app.api` section of kiwissh.yaml is read (for the port the API listens on).
"""

import json
import sys
import urllib.error
import urllib.request

import yaml
from app.core.config import ApiConfig, KiwiSSHYamlLoader, Settings

### Stay below the HEALTHCHECK --timeout so the reason is still printed when the API is slow
REQUEST_TIMEOUT_SECONDS = 8


def _resolve_api_address() -> tuple[str, int]:
    """Return the host and port the API listens on, according to app.api in kiwissh.yaml."""
    ### Load kiwissh.yaml config
    config_file = Settings().config_dir / "kiwissh.yaml"
    with open(config_file, encoding="utf-8") as f:
        file_content = yaml.load(f, Loader=KiwiSSHYamlLoader) or {}

    api = ApiConfig(**(file_content.get("app") or {}).get("api") or {})
    host = "127.0.0.1" if api.host in {"", "0.0.0.0", "::"} else api.host # Use loopback for wildcard addresses
    ### IPv6 need brackets in URLs
    if ":" in host:
        host = f"[{host}]"
    return host, api.port

### =========================================================================================================

def main() -> int:
    """Run the container healthcheck by querying the readiness endpoint."""
    try:
        host, port = _resolve_api_address()
    except Exception as ex:
        print(f"Could not read app.api from kiwissh.yaml: {ex}")
        return 1

    url = f"http://{host}:{port}/api/v1/health/ready"
    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = json.load(response)
    except urllib.error.HTTPError as ex:
        ### 503 carries the failed checks in its body
        try:
            checks = json.load(ex).get("checks", {})
            failed = sorted(name for name, ok in checks.items() if not ok)
        except Exception:
            failed = []
        print(f"Not ready (HTTP {ex.code}), failed checks: {', '.join(failed) or 'unknown'}")
        return 1
    except Exception as ex:
        print(f"Readiness endpoint {url} not reachable: {ex}")
        return 1

    if not body.get("ready"):
        print("Not ready")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
