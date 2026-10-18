import pytest
from datetime import datetime, timedelta, timezone

from tokens.tokens import TTL, is_expired, issue


def test_ac1_naive_tolerant():
    """AC1: Tolerate naive inputs by treating them as UTC."""
    now = datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc)
    token = issue(now)
    naive_at = datetime(2023, 1, 1, 13, 0)  # No timezone
    assert is_expired(token, naive_at) is True


def test_ac2_tz_aware_utc():
    """AC2: The service is tz-aware UTC everywhere."""
    now = datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc)
    token = issue(now)
    aware_at = datetime(2023, 1, 1, 13, 0, tzinfo=timezone.utc)
    assert is_expired(token, aware_at) is True


def test_ac3_issue_unchanged():
    """AC3: Do not change issue()."""
    now = datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc)
    expected = now + TTL
    assert issue(now) == {"expires_at": expected}
