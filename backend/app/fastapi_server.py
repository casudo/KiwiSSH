"""FastAPI Server"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import api_router_v1
from app.core import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler.

    Everything before yield: runs on startup
    Everything after yield: runs on shutdown
    """
    ### Startup
    settings = get_settings()

    print(f"Starting Project Downtown v{__version__}")
    print(f"Config directory: {settings.config_dir}")
    print(f"Debug mode: {settings.debug}")
    print(f"Loaded {len(settings.vendors)} vendor configurations")
    print(f"Loaded {len(settings.ssh_profiles)} SSH profiles")
    ### TODO: Device Count

    yield

    ### Shutdown
    print("Shutting down Project Downtown")


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
        redoc_url="/redoc",
    )

    ### Configure CORS (load from config or use defaults)
    cors_origins = settings.app_config.get("api", {}).get(
        "cors_origins",
        [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
    )

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
        host="127.0.0.1",
        port=settings.api_port,
        log_level=settings.debug,
    )
