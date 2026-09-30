"""Tests for billing.plans."""

from billing.plans import is_enterprise, is_known, parse_webhook


def test_enterprise_detected_from_webhook_payload():
    payload = parse_webhook("plan=Enterprise&seats=40")
    assert is_enterprise(payload["plan"]) is True


def test_non_enterprise_plans_are_rejected():
    assert is_enterprise("pro") is False
    assert is_enterprise("free") is False


def test_known_plan_from_webhook_payload():
    payload = parse_webhook("plan=PRO")
    assert is_known(payload["plan"]) is True
