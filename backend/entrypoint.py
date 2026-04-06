"""Application entrypoint.

TODO: First implementation, need maintenance"""

import logging
import sys
from dotenv import load_dotenv

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
    """Validate the YAML configuration.
    
    Raises:
        ValueError: If configuration is invalid
    """
    from app.core.config import get_settings
    
    settings = get_settings()

    ### Validate each group has required fields
    errors = []
    for group_name, group_config in settings.groups.items():
        if not group_config.vendor:
            errors.append(f"Group '{group_name}' missing required 'vendor'")
        if not group_config.ssh_profile:
            errors.append(f"Group '{group_name}' missing required 'ssh_profile'")
        if not group_config.username:
            errors.append(f"Group '{group_name}' missing required 'username'")
        if not group_config.password:
            errors.append(f"Group '{group_name}' missing required 'password'")

    ### Validate source selection (exactly one source is required)
    has_file_source = bool(settings.sources and settings.sources.file is not None)
    has_postgres_source = bool(settings.sources and settings.sources.postgres is not None)

    if has_file_source and has_postgres_source:
        errors.append("Configure only one source under 'sources': either 'file' or 'postgres', not both")
    if not has_file_source and not has_postgres_source:
        errors.append("One source is required under 'sources': configure either 'file' or 'postgres'")

    if has_file_source:
        file_source_path = str(settings.sources.file).strip()
        if not file_source_path:
            errors.append("sources.file must be a non-empty path")

    if has_postgres_source:
        postgres_source = settings.sources.postgres
        if not str(postgres_source.host).strip():
            errors.append("sources.postgres.host is required")
        if not (1 <= postgres_source.port <= 65535):
            errors.append("sources.postgres.port must be between 1 and 65535")
        if not str(postgres_source.database).strip():
            errors.append("sources.postgres.database is required")
        if not str(postgres_source.table).strip():
            errors.append("sources.postgres.table is required")
        if not str(postgres_source.username).strip():
            errors.append("sources.postgres.username is required")
        if not str(postgres_source.password).strip():
            errors.append("sources.postgres.password is required")

    ### Validate application database configuration
    app_db = settings.application_database
    if app_db is None:
        errors.append("Missing required 'application_database' section")
    else:
        if not str(app_db.host).strip():
            errors.append("application_database.host is required")
        if not (1 <= app_db.port <= 65535):
            errors.append("application_database.port must be between 1 and 65535")
        if not str(app_db.database).strip():
            errors.append("application_database.database is required")
        if not str(app_db.username).strip():
            errors.append("application_database.user is required")
        if not str(app_db.password).strip():
            errors.append("application_database.password is required")
    
    if errors:
        raise ValueError("Invalid configuration:\n  " + "\n  ".join(errors))

    logger.info("✓ YAML configuration valid")
    logger.info(f"✓ Groups configured: {len(settings.groups)}")
    logger.info(f"✓ Vendors available: {len(settings.vendors)}")
    logger.info(f"✓ SSH profiles available: {len(settings.ssh_profiles.get('profiles', {}))}")
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
        import uvicorn
        from app.core.config import get_settings
        
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
