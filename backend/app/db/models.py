"""SQLAlchemy database models for backup jobs."""

from sqlalchemy import Column, String, DateTime, Text, Integer
from sqlalchemy.ext.declarative import declarative_base
from app.utils.timezone import get_utc_now

Base = declarative_base()


class BackupJob(Base):
    """Backup job record for persistent storage."""

    __tablename__ = "backup_jobs"

    id = Column(String(255), primary_key=True, index=True)  # Git commit hash or UUID# TODO: What exactly is the UUID?
    device_name = Column(String(255), nullable=False, index=True)
    group = Column(String(255), nullable=False, index=True)
    status = Column(String(32), nullable=False, index=True)  # success, failed
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True, default=lambda: get_utc_now())
    error_message = Column(Text, nullable=True)
    config_size_bytes = Column(Integer, nullable=True)
    metadata_output = Column(Text, nullable=True)

    def __repr__(self):
        return f"<BackupJob {self.device_name} {self.status} {self.timestamp}>"


class FavoriteDevice(Base):
    """Favorite device marker persisted per device name."""

    __tablename__ = "favorite_devices"

    device_name = Column(String(255), primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: get_utc_now())

    def __repr__(self):
        return f"<FavoriteDevice {self.device_name}>"
