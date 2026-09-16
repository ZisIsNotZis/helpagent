"""Tests for order placement validation."""

import pytest

from orders.errors import OrderValidationError
from orders.service import place_order


def test_empty_order_is_rejected_with_domain_error():
    with pytest.raises(OrderValidationError):
        place_order({"id": "A-1", "items": []})


def test_oversized_order_is_rejected_with_domain_error():
    with pytest.raises(OrderValidationError):
        place_order({"id": "A-2", "items": ["item"] * 25})
