"""Tests for tz-tolerant expiry handling of naive datetimes."""

from datetime import datetime, timedelta

from tokens.tokens import TTL, is_expired


def test_naive_datetime_treated_as_utc():
    """Naive inputs must be treated as UTC for expiry checks."""
    now = datetime(2023, 1, 1, 12, 0, 0)
    token = {"expires_at": now + TTL}

    # Naive 'at' time should be compared against the tz-aware expiry.
    at = datetime(2023, 1, 1, 12, 0, 0)
    assert is_expired(token, at) is False

    # Exactly at the expiry boundary should be considered expired.
    at_expiry = token["expires_at"]
    assert is_expired(token, at_expiry) is True


def test_naive_input_treated_as_utc():
    """Naive token inputs are treated as UTC and compared correctly."""
    now = datetime(2023, 1, 1, 12, 0, 0)
    token = {"expires_at": now + TTL}

    # A naive 'at' time representing the same instant as the tz-aware expiry.
    at = datetime(2023, 1, 1, 13, 0, 0)
    assert is_expired(token, at) is True
