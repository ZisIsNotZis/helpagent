"""One-time tokens with an expiry."""

from datetime import datetime, timedelta

TTL = timedelta(hours=1)


def issue(now: datetime) -> dict:
    """Issue a token expiring TTL after `now` (tz-aware UTC everywhere)."""
    return {"expires_at": now + TTL}


def is_expired(token: dict, at: datetime) -> bool:
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return at >= token["expires_at"]

from datetime import timezone