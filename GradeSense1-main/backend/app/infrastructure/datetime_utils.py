from datetime import datetime, timezone

def _iso_now() -> str:
    """Returns current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()

def _utc_now() -> datetime:
    """Returns current UTC datetime object."""
    return datetime.now(timezone.utc)
