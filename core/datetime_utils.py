"""Shared UTC normalization for database timestamps."""

from datetime import datetime, timezone


def as_utc(value: datetime) -> datetime:
    """Treat naive SAGE/SQLite timestamps as UTC; preserve aware instants in UTC."""
    if value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
