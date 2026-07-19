"""Database connection and initialization."""

import logging
from pathlib import Path

from sqlalchemy import create_engine, event
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
        engine = _create_sqlite_engine(settings.database_url, app_db.path)
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


def _create_sqlite_engine(database_url: str, db_path: str) -> "object":
    """Create a SQLAlchemy engine for a SQLite backend.

    Ensures the parent directory exists and enables pragmas (WAL journaling and
    a busy timeout) so the multi-threaded backend can share the database file.
    """
    ### Ensure the parent directory exists so SQLite can create the file
    parent = Path(db_path).expanduser().parent
    if parent and not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)

    logger.info("Connecting to SQLite application database at '%s'", db_path)

    sqlite_engine = create_engine(
        database_url,
        echo=False,
        future=True,
        pool_pre_ping=True,
        ### SQLAlchemy uses a single connection per thread guard by default
        ## the backend runs multiple worker threads, so allow cross-thread usage
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(sqlite_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        """Enable WAL mode and a busy timeout for better concurrent access."""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    return sqlite_engine


def get_db() -> Generator[Session, None, None]:
    """Get database session for dependency injection."""
    if SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
