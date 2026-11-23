"""Prometheus metrics endpoint.

Only served when `app.metrics` is enabled.
"""

from fastapi import APIRouter, Response
from fastapi.responses import PlainTextResponse

## WIP: own metric service import

router = APIRouter()


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics() -> Response:
    """Prometheus metrics."""
    ...
