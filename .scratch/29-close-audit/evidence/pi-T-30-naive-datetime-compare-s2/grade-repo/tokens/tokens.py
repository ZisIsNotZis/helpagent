"""One-time tokens with an expiry."""

from datetime import datetime, timedelta, timezone

TTL = timedelta(hours=1)


def issue(now: datetime) -> dict:
    """Issue a token expiring TTL after `now` (tz-aware UTC everywhere)."""
    return {"expires_at": now + TTL}


def is_expired(token: dict, at: datetime) -> bool:
    """Check whether the token is expired.

    Naive datetimes from ops callers are treated as UTC, matching the
    tz-aware UTC service everywhere.
    """
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return at >= token["expires_at"]
