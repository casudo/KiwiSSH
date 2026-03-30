"""Service for persisting favorite devices in the application database."""

from sqlalchemy.orm import Session

from app.db.models import FavoriteDevice


class FavoriteService:
    """Service for managing favorite devices."""

    @staticmethod
    def list_favorites(db: Session) -> list[str]:
        """Return all favorite device names."""
        favorites = db.query(FavoriteDevice).order_by(FavoriteDevice.device_name).all()
        return [favorite.device_name for favorite in favorites]

    @staticmethod
    def add_favorite(db: Session, device_name: str) -> bool:
        """Add a favorite device if it does not already exist.

        Returns:
            True if created, False if it already existed.
        """
        existing = db.query(FavoriteDevice).filter(FavoriteDevice.device_name == device_name).first()
        if existing:
            return False

        db.add(FavoriteDevice(device_name=device_name))
        db.commit()
        return True

    @staticmethod
    def remove_favorite(db: Session, device_name: str) -> bool:
        """Remove a favorite device.

        Returns:
            True if removed, False if it did not exist.
        """
        deleted = db.query(FavoriteDevice).filter(FavoriteDevice.device_name == device_name).delete(
            synchronize_session=False
        )
        db.commit()
        return deleted > 0

### Singleton instance
favorite_service = FavoriteService()
