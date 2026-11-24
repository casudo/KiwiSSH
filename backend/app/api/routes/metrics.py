"""Prometheus metrics endpoint.

Only served when `app.metrics` is enabled.
"""

from fastapi import APIRouter, Response
from fastapi.responses import PlainTextResponse

from app.services.metrics_service import metrics_service

router = APIRouter()


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics() -> Response:
    """Get device, job and queue statistics in the Prometheus text format."""
    return Response(content=await metrics_service.render(), media_type=metrics_service.content_type)
