from billing.plans import is_enterprise, parse_webhook


def test_parse_webhook_enterprise():
    payload = "plan=enterprise&other=value"
    parsed = parse_webhook(payload)
    assert parsed["plan"] == "enterprise"


def test_is_enterprise_from_webhook():
    parsed = parse_webhook("plan=enterprise")
    assert is_enterprise(parsed["plan"])


def test_is_enterprise_known_plan():
    assert is_enterprise(PLAN_ENTERPRISE) is True
    assert is_enterprise(PLAN_FREE) is False
    assert is_enterprise(PLAN_PRO) is False


def test_is_enterprise_unknown_plan():
    assert is_enterprise("unknown") is False
    assert is_enterprise("ENTERPRISE") is True
