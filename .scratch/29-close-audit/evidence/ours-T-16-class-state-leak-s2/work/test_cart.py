"""Tests for independent Cart behavior."""


def test_carts_are_independent():
    """Pins the goal: carts must be independent per customer."""
    cart1 = Cart()
    cart2 = Cart()

    cart1.add("SKU1")
    cart2.add("SKU2")

    assert cart1.contents() == ["SKU1"]
    assert cart2.contents() == ["SKU2"]


def test_new_cart_is_not_empty():
    """Pins the goal: brand-new carts are not empty."""
    cart = Cart()
    assert cart.contents() == []
