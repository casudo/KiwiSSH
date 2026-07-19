"""Database connection and initialization."""

import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.db.models import Base
from typing import Generator

from app.core import Settings

logger = logging.getLogger(__name__)

### Global engine and SessionLocal will be set after config is loaded
engine = None
SessionLocal = None


def init_database(settings: Settings) -> None:
    """Initialize the application database connection and create application tables.

    Supports both PostgreSQL and SQLite backends, selected via
    `application_database.type` in the configuration.
    """
    global engine, SessionLocal

    app_db = settings.application_database

    if app_db.type == "sqlite":
        ...
    elif app_db.type == "postgresql":
        engine = _create_postgres_engine(settings, app_db)
    else:
        raise ValueError(f"Unsupported database type: {app_db.type}")

    ### Create tables
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    logger.info("Application database initialized successfully")


def _create_postgres_engine(settings: Settings, app_db) -> "object":
    """Create a SQLAlchemy engine for a PostgreSQL backend."""
    logger.info(
        "Connecting to PostgreSQL application database '%s' on %s:%s as user '%s'",
        app_db.database,
        app_db.host,
        app_db.port,
        app_db.username,
    )

    return create_engine(
        settings.database_url,
        echo=False,
        future=True,
        pool_pre_ping=True,
        ### Increase if QueuePool error
        pool_size=20,
        max_overflow=20,
        pool_timeout=10,
        connect_args={"connect_timeout": 5},
    )

    ### Create tables
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    logger.info("Application database initialized successfully")


def get_db() -> Generator[Session, None, None]:
    """Get database session for dependency injection."""
    if SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
