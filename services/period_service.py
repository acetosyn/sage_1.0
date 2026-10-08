"""Calendar boundaries in UTC, shared by dashboards, comparisons and exports."""
from datetime import datetime, timedelta, timezone

PERIODS = {"all", "daily", "weekly", "monthly", "quarterly", "yearly"}


def shift_month(value, delta):
    year, month = divmod(value.year * 12 + value.month - 1 + delta, 12)
    return value.replace(year=year, month=month + 1, day=1)


def period_bounds(period="all", now=None):
    if period not in PERIODS: raise ValueError("Choose a valid reporting period.")
    now = now or datetime.now(timezone.utc)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "all": return None, None
    if period == "daily": return day, day + timedelta(days=1)
    if period == "weekly":
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(days=7)
    if period == "monthly":
        start = day.replace(day=1)
        return start, shift_month(start, 1)
    if period == "quarterly":
        start = day.replace(day=1, month=(day.month - 1) // 3 * 3 + 1)
        return start, shift_month(start, 3)
    start = day.replace(day=1, month=1)
    return start, start.replace(year=start.year + 1)


def previous_bounds(period, now=None):
    start, end = period_bounds(period, now)
    if start is None: return None, None
    delta = {"monthly": -1, "quarterly": -3, "yearly": -12}.get(period)
    return (shift_month(start, delta), start) if delta else (start - (end - start), start)
