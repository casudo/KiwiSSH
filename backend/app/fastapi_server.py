"""FastAPI Server"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import api_router_v1
from app.core import get_settings
from app.core.logging import configure_logging
from app.services import source_service
from app.services.backup_scheduler_service import backup_scheduler_service
from app.services.backup_job_service import backup_job_service
from app.db.database import init_database

### Load .env file early to ensure env vars are available
load_dotenv()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler.

    Everything before yield: runs on startup
    Everything after yield: runs on shutdown
    """
    ### Startup
    
    ## Clear caches before starting to ensure we have the latest config and data
    get_settings.cache_clear()
    source_service.invalidate_cache()
    
    settings = get_settings()
    configure_logging(debug=settings.app.debug)

    logger.info(f"Starting Project Downtown v{__version__}")
    logger.info(f"Config directory: {settings.config_dir}")
    logger.info(f"Debug mode: {settings.app.debug}")
    logger.info(f"Loaded {len(settings.vendors)} vendor configurations")
    logger.info(f"Loaded {len(settings.ssh_profiles.get('profiles', {}))} SSH profiles")
    logger.info(f"Max concurrent SSH sessions: {settings.app.threads}")
    logger.info(f"Global backup schedule: {settings.app.schedule.cron} ({settings.app.schedule.timezone})")

    ### Load and log device count
    devices = await source_service.get_all_devices()
    logger.info(f"Loaded {len(devices)} devices")
    
    ### Initialize PostgreSQL application database
    logger.info("Initializing application database connection...")
    init_database(settings)
    
    ### Startup recovery: mark stuck jobs as failed
    from app.db.database import SessionLocal
    if SessionLocal is not None:
        try:
            db = SessionLocal()
            try:
                stuck_jobs_count = backup_job_service.mark_stuck_jobs_as_failed(db)
                if stuck_jobs_count > 0:
                    logger.warning(f"Marked {stuck_jobs_count} stuck backup job(s) as failed during startup recovery")
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Failed to clean up stuck jobs during startup: {e}")
    
    ### Start backup scheduler
    backup_scheduler_service.start_scheduler(devices)

    yield

    ### Shutdown
    logger.info("Shutting down Project Downtown")
    backup_scheduler_service.stop_scheduler()


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

### TODO: Remove since we now have the entrypoint.py for starting the server?
if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        app,
        host=settings.app.api.host,
        port=settings.app.api.port,
        log_level="debug" if settings.app.debug else "info",
    )
