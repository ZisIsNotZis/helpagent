"""Tests for webhook-driven plan detection."""

from billing.plans import is_enterprise, parse_webhook


def test_parse_webhook_normalizes_plan_value():
    payload = "plan=Enterprise&other=value"
    parsed = parse_webhook(payload)
    assert parsed["plan"] == "enterprise"


def test_is_enterprise_matches_normalized_plan():
    parsed = parse_webhook("plan=Enterprise")
    assert is_enterprise(parsed["plan"])


def test_is_enterprise_false_for_non_enterprise():
    parsed = parse_webhook("plan=pro")
    assert not is_enterprise(parsed["plan"])
