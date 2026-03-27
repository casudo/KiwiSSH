"""Timezone utilities for consistent timestamp handling across the application."""

import os
from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo


def get_configured_tz() -> tzinfo:
    """Get the configured timezone from TZ environment variable, defaulting to UTC.

    Returns:
        tzinfo: The configured timezone
    """
    tz_name = os.getenv("TZ", "UTC")
    try:
        return ZoneInfo(tz_name)
    except Exception:
        ### Fallback to UTC if timezone is invalid
        return timezone.utc


def get_now() -> datetime:
    """Get current datetime in the configured timezone.

    Returns:
        datetime: Current time in configured timezone
    """
    return datetime.now(get_configured_tz())


def get_utc_now() -> datetime:
    """Get current datetime in UTC (for database storage).

    Always use this for storing timestamps in the database to maintain consistency,
    even if the application timezone is different.

    Returns:
        datetime: Current time in UTC
    """
    return datetime.now(timezone.utc)
