"""FastAPI Server"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import api_router_v1
from app.core import get_settings
from app.core.logging import configure_logging
from app.services import source_service
from app.db.database import init_database

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler.

    Everything before yield: runs on startup
    Everything after yield: runs on shutdown
    """
    ### Startup
    settings = get_settings()
    configure_logging(debug=settings.app.debug)
    

    ## Clear caches to ensure fresh load from .env file
    get_settings.cache_clear()
    source_service.invalidate_cache()

    logger.info(f"Starting Project Downtown v{__version__}")
    logger.info(f"Config directory: {settings.config_dir}")
    logger.info(f"Debug mode: {settings.app.debug}")
    logger.info(f"Loaded {len(settings.vendors)} vendor configurations")
    logger.info(f"Loaded {len(settings.ssh_profiles.get('profiles', {}))} SSH profiles")

    ### Load and log device count
    devices = await source_service.get_all_devices()
    logger.info(f"Loaded {len(devices)} devices")
    
    ### Initialize PostgreSQL application database
    logger.info("Initializing application database connection...")
    init_database(settings)

    yield

    ### Shutdown
    logger.info("Shutting down Project Downtown")


### Definde FastAPI app
def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Project Downtown",
        description="Network configuration backup application",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )

    ### Configure CORS (load from config or use defaults)
    cors_origins = settings.app.api.cors_origins or [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],  # TODO: Restrict
        allow_headers=["*"],
    )

    ### Include API routes
    app.include_router(api_router_v1, prefix="/api/v1")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        app,
        host=settings.app.api.host,
        port=settings.app.api.port,
        log_level="debug" if settings.app.debug else "info",
    )
