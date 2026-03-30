"""Application entrypoint.

TODO: First implementation, need maintenance"""

import logging
import sys

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
        if not str(app_db.user).strip():
            errors.append("application_database.user is required")
        if not str(app_db.password).strip():
            errors.append("application_database.password is required")
    
    if errors:
        raise ValueError("Invalid configuration:\n  " + "\n  ".join(errors))

    logger.info("✓ YAML configuration valid")
    logger.info(f"✓ Groups configured: {len(settings.groups)}")
    logger.info(f"✓ Vendors available: {len(settings.vendors)}")
    logger.info(f"✓ SSH profiles available: {len(settings.ssh_profiles.get('profiles', {}))}")
    logger.info("✓ Application database configured")

def main() -> int:
    """Validate application configuration and start the application.
    
    It only validates stuff which is directly in the apps control (e.g. YAML config files). External device sources will not be validated by the entrypoint. If an error should occur there, the repesctive modules will return an error and the user can fix the issue from there.
    
    Returns:
        Exit code (0 for success, 1 for validation failure)
    """
    try:
        logger.info("Project Downtown - Validating YAML configuration...")

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
            "app.fastapi_server:app", # Why :app here? 
            host=settings.api.host,
            port=settings.api.port,
            reload=settings.app.debug,
        ) # TODO: Do we need to set the app settings here? fastapi_server.py starts the app with the exact same settings
        return 0
        
    # TODO: Add custom error (e.g. ConfigurationError) and catch it here to provide better error messages
    except ValueError as e:
        logger.error(f"Configuration validation failed:\n{e}")
        return 1
    except Exception as e:
        logger.error(f"Startup failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
