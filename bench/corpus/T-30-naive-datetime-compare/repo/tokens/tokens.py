"""One-time tokens with an expiry."""

from datetime import datetime, timedelta

TTL = timedelta(hours=1)


def issue(now: datetime) -> dict:
    """Issue a token expiring TTL after `now` (tz-aware UTC everywhere)."""
    return {"expires_at": now + TTL}


def is_expired(token: dict, at: datetime) -> bool:
    return at >= token["expires_at"]
