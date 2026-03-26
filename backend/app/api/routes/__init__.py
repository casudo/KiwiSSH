"""API route aggregation."""

from fastapi import APIRouter

from app.api.routes import backups, devices, health, vendors

api_router_v1 = APIRouter()

api_router_v1.include_router(
    health.router,
    prefix="/health",
    tags=["health"],
)

api_router_v1.include_router(
    devices.router,
    prefix="/devices",
    tags=["devices"],
)

api_router_v1.include_router(
    backups.router,
    prefix="/backups",
    tags=["backups"],
)

api_router_v1.include_router(
    vendors.router,
    prefix="/vendors",
    tags=["vendors"],
)
