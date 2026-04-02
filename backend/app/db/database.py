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
    """Initialize PostgreSQL connection and create application tables."""
    global engine, SessionLocal

    app_db = settings.application_database
    logger.info(
        "Connecting to application database '%s' on %s:%s as user '%s'",
        app_db.database,
        app_db.host,
        app_db.port,
        app_db.username,
    )

    engine = create_engine(
        settings.database_url,
        echo=False,
        future=True,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )

    ### Create tables
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    logger.info("Application database initialized successfully (existing DB expected)")


def get_db() -> Generator[Session, None, None]:
    """Get database session for dependency injection."""
    if SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
