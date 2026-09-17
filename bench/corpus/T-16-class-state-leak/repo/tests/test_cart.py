"""Cart isolation tests."""

from cart.cart import Cart


def test_new_cart_starts_empty():
    assert Cart().contents() == []


def test_carts_are_independent():
    a = Cart()
    b = Cart()
    a.add("sku-1")
    assert a.contents() == ["sku-1"]
    assert b.contents() == []
