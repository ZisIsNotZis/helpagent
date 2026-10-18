"""One-time tokens with an expiry."""

from datetime import datetime, timedelta

TTL = timedelta(hours=1)


def issue(now: datetime) -> dict:
    """Issue a token expiring TTL after `now` (tz-aware UTC everywhere)."""
    return {"expires_at": now + TTL}


def is_expired(token: dict, at: datetime) -> bool:
    # Tolerate naive inputs by treating them as UTC.
    if at.tzinfo is None:
        at = at.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return at >= token["expires_at"]
