"""Canonical datetime formatting and parsing for the Trache cache layer."""

from __future__ import annotations

from datetime import datetime


def fmt_dt(dt: datetime | str | None) -> str | None:
    """Format a datetime to ISO string, or return None/str as-is.

    - None -> None
    - str  -> returned unchanged (passthrough for already-serialised values)
    - datetime -> 'YYYY-MM-DDTHH:MM:SSZ' (UTC normalised)
    """
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is not None and dt.utcoffset() is not None:
        from datetime import timezone

        if dt.utcoffset().total_seconds() != 0:
            dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_dt(val: str | None) -> datetime | None:
    """Parse an ISO datetime string, or return None.

    Handles Z suffix and strips fractional seconds for Python 3.10 compat.
    """
    if val is None:
        return None
    val = val.replace("Z", "+00:00")
    if "." in val:
        dot = val.index(".")
        tz_start = len(val)
        for i in range(dot + 1, len(val)):
            if val[i] in ("+", "-"):
                tz_start = i
                break
        val = val[:dot] + val[tz_start:]
    return datetime.fromisoformat(val)
