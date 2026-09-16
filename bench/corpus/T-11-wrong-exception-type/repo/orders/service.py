"""Order validation and placement."""

from orders.errors import OrderValidationError

MAX_ITEMS = 20


def place_order(order: dict) -> str:
    """Place ``order`` and return its confirmation id.

    Validation failures raise :class:`OrderValidationError` — integrations map
    that error, never built-in exceptions.
    """
    if not order.get("items"):
        raise OrderValidationError("an order needs at least one item")
    if len(order["items"]) > MAX_ITEMS:
        raise ValueError("order exceeds the item limit")
    return f"OK-{order['id']}"
