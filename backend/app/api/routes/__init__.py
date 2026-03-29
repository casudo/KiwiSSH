"""API route aggregation."""

from fastapi import APIRouter

from app.api.routes import backups, devices, health, ssh_profiles, vendors

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

api_router_v1.include_router(
    ssh_profiles.router,
    prefix="/ssh-profiles",
    tags=["ssh_profiles"],
)
