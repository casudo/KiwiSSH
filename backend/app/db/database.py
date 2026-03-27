"""Database connection and initialization."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from app.db.models import Base
from typing import Generator

### Global engine and SessionLocal will be set after config is loaded
engine = None
SessionLocal = None


def init_database(database_url: str) -> None:
    """Initialize database connection and create tables.

    Args:
        database_url: SQLAlchemy database URL (sqlite:/// or postgresql://)

    NOTE: postgresql:// not tested yet!!
    """
    global engine, SessionLocal

    engine = create_engine(database_url, echo=False)

    ### Enable foreign keys for SQLite
    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    ### Create tables
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    print(f"✓ Database initialized: {database_url}")


def get_db() -> Generator[Session, None, None]:
    """Get database session for dependency injection."""
    if SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
