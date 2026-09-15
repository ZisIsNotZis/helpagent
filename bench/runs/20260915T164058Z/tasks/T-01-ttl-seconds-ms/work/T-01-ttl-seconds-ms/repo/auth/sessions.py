"""Session creation and expiry."""

import secrets
from datetime import datetime, timedelta, timezone

from . import config


def create_session(user_id: str, now: datetime | None = None) -> dict:
    """Create a session for ``user_id`` starting at ``now`` (UTC now by default)."""
    now = now or datetime.now(timezone.utc)
    return {
        "user_id": user_id,
        "token": secrets.token_hex(16),
        "created_at": now,
        "expires_at": now + timedelta(seconds=config.SESSION_TTL_SECONDS),
    }


def is_expired(session: dict, at: datetime | None = None) -> bool:
    """True when ``session`` is expired at ``at`` (UTC now by default)."""
    at = at or datetime.now(timezone.utc)
    return at >= session["expires_at"]
