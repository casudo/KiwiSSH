"""Application entrypoint.

NOTE: This module is intentionally small for now.
It may be removed in the future if startup stays minimal,
or extended with dedicated environment variable checks.
"""

import logging
import sys
import uvicorn
from dotenv import load_dotenv
from app.core.config import get_settings

### Load .env file early to set environment variables
load_dotenv()

### Set up logging early
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

### TODO: Placeholder and not actively used
class ConfigurationError(Exception):
    """Custom exception for configuration validation errors."""
    pass


def validate_configuration() -> None:
    """Validate YAML configuration by loading settings and relying on model validators."""
    
    settings = get_settings()

    has_postgres_source = bool(settings.sources and settings.sources.postgres is not None)
    logger.info(f"✓ Device source configured: {'postgres' if has_postgres_source else 'file'}")
    logger.info("✓ Application database configured")

def main() -> int:
    """Validate application configuration and start the application.
    
    It only validates stuff which is directly in the apps control (e.g. YAML config files). External device sources will not be validated by the entrypoint. If an error should occur there, the repesctive modules will return an error and the user can fix the issue from there.
    
    Returns:
        Exit code (0 for success, 1 for validation failure)
    """
    try:
        logger.info("KiwiSSH - Validating YAML configuration...")

        ### Step 1: Validate envionment variables
        # TODO

        ### Step 2: Validate YAML configuration
        validate_configuration()
        
        logger.info("✓ All validations passed")
        logger.info("Starting FastAPI server...")
        
        ### Start the FastAPI server        
        settings = get_settings()
        
        uvicorn.run(
            "app.fastapi_server:app",
            host=settings.app.api.host,
            port=settings.app.api.port,
            reload=settings.app.debug,  # Auto-reload debug/development mode
            log_level="debug" if settings.app.debug else "info",
        )
        return 0
        
    ### TODO: Add custom error (e.g. ConfigurationError) and catch it here to provide better error messages
    except ValueError as e:
        logger.error(f"Configuration validation failed:\n{e}")
        return 1
    except Exception as e:
        logger.error(f"Startup failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
