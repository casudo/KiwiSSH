"""API route aggregation."""

from fastapi import APIRouter

from app.api.routes import health, devices, backups, vendors

api_router = APIRouter()

api_router.include_router(
    health.router,
    prefix="/health",
    tags=["health"],
)

api_router.include_router(
    devices.router,
    prefix="/devices",
    tags=["devices"],
)

api_router.include_router(
    backups.router,
    prefix="/backups",
    tags=["backups"],
)

api_router.include_router(
    vendors.router,
    prefix="/vendors",
    tags=["vendors"],
)
