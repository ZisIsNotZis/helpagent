"""Tests for the session layer."""

from datetime import datetime, timedelta, timezone

from auth.sessions import create_session, is_expired


def _utc(y: int, mo: int, d: int, h: int, mi: int = 0, s: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)


def test_fresh_session_is_not_expired():
    created = _utc(2025, 1, 1, 12, 0, 0)
    session = create_session("u-1", now=created)
    assert not is_expired(session, at=created + timedelta(seconds=30))


def test_session_lives_one_hour():
    created = _utc(2025, 1, 1, 12, 0, 0)
    session = create_session("u-1", now=created)
    assert session["expires_at"] == created + timedelta(hours=1)
