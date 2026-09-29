"""Known plans and plan predicates."""

PLAN_FREE = "free"
PLAN_PRO = "pro"
PLAN_ENTERPRISE = "enterprise"

KNOWN_PLANS = (PLAN_FREE, PLAN_PRO, PLAN_ENTERPRISE)


def parse_webhook(payload: str) -> dict:
    """Parse a flat ``key=value&key=value`` webhook payload into a dict."""
    out: dict[str, str] = {}
    for field in payload.split("&"):
        key, _, value = field.partition("=")
        out[key] = value.strip().lower()
    return out


def is_enterprise(plan: str) -> bool:
    """True when ``plan`` is the enterprise plan."""
    return plan.strip().lower() == PLAN_ENTERPRISE


def is_known(plan: str) -> bool:
    """True when ``plan`` is one of the known plans."""
    return plan in KNOWN_PLANS
