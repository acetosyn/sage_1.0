"""Shared SAGE date/time helpers.

All server-side business timestamps are normalized to UTC for storage. Browser UI controls
send offset-aware ISO timestamps, and the front end renders them in the user's local time.
"""

from datetime import datetime, timezone


def as_utc(value: datetime) -> datetime:
    """Treat naive SAGE/SQLite timestamps as UTC; preserve aware instants in UTC."""
    if value.utcoffset() is None: return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_client_datetime(value, fallback=None):
    """Parse an HTML/browser ISO timestamp and normalize it to UTC.

    Browsers submit an explicit offset through the SAGE JavaScript helpers. A naive value is
    interpreted as UTC only as a defensive fallback for older clients.
    """
    text = str(value or "").strip()
    if not text: return fallback
    try: parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc: raise ValueError("Enter a valid date and time.") from exc
    return as_utc(parsed)
