"""Tests for webhook-driven plan detection."""

from billing.plans import is_enterprise, parse_webhook


def test_webhook_enterprise_plan_detection():
    """A billing webhook with the enterprise plan value flips the customer."""
    payload = "plan=enterprise&customer=123"
    parsed = parse_webhook(payload)
    assert is_enterprise(parsed["plan"])


def test_webhook_free_plan_not_enterprise():
    """A billing webhook with a free plan does not flip the customer."""
    payload = "plan=free&customer=123"
    parsed = parse_webhook(payload)
    assert not is_enterprise(parsed["plan"])


def test_webhook_pro_plan_not_enterprise():
    """A billing webhook with a pro plan does not flip the customer."""
    payload = "plan=pro&customer=123"
    parsed = parse_webhook(payload)
    assert not is_enterprise(parsed["plan"])


def test_webhook_case_normalized():
    """Plan string comparison is case-insensitive as required."""
    payload = "plan=ENTERPRISE&customer=123"
    parsed = parse_webhook(payload)
    assert is_enterprise(parsed["plan"])


def test_webhook_whitespace_normalized():
    """Plan string comparison is whitespace-insensitive as required."""
    payload = "plan= enterprise & customer=123"
    parsed = parse_webhook(payload)
    assert is_enterprise(parsed["plan"])
