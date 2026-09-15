"""
Shared UTC time helpers.

Conventions:
- Database timestamp columns use naive UTC datetimes to match the current
  schema (`TIMESTAMP WITHOUT TIME ZONE`).
- In-memory business logic that needs timezone awareness uses UTC-aware
  datetimes.
- API/log payloads should prefer ISO 8601 UTC strings.`
"""
from datetime import datetime, timezone

def utc_now() -> datetime:
    """Return a timezone-aware UTC datetime"""
    return datetime.now(timezone.utc)

def utc_now_naive() -> datetime:
    """Return a naive UTC datetime for database reads/writes"""
    return utc_now().replace(tzinfo=None)

def as_utc_aware(value: datetime) -> datetime:
    """Coerce a datetime to timezone-aware UTC"""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

def utc_isoformat(value: datetime | None = None) -> str:
    """Serialize a datetime as an ISO 8601 UTC string"""
    current = as_utc_aware(value) if value is not None else utc_now()
    return current.isoformat().replace("+00:00", "Z")