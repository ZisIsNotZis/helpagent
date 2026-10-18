"""Expiry tests (the service passes tz-aware UTC datetimes)."""

from datetime import datetime, timedelta, timezone

from tokens.tokens import issue, is_expired


def _utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


def test_naive_input_treated_as_utc_not_expired():
    t = issue(_utc(2025, 3, 1, 12))
    naive = datetime(2025, 3, 1, 12, 30)
    assert not is_expired(t, naive)


def test_naive_expired_input():
    t = issue(_utc(2025, 3, 1, 12))
    naive = datetime(2025, 3, 1, 13, 1)
    assert is_expired(t, naive)
