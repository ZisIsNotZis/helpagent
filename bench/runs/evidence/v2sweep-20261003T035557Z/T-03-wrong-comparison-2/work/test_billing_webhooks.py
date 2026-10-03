"""Tests for webhook-driven plan detection."""

import pytest

from billing.plans import is_enterprise, parse_webhook


PLAN_ENTERPRISE = "enterprise"


def test_parse_webhook_normalizes_plan_value():
    payload = "plan=enterprise&other=value"
    parsed = parse_webhook(payload)
    assert parsed["plan"] == PLAN_ENTERPRISE


def test_is_enterprise_matches_normalized_plan():
    assert is_enterprise(PLAN_ENTERPRISE)


def test_is_enterprise_false_for_other_plans():
    assert not is_enterprise("free")
    assert not is_enterprise("pro")


def test_webhook_plan_detection_flips_enterprise():
    payload = "plan=enterprise"
    parsed = parse_webhook(payload)
    assert is_enterprise(parsed["plan"])
