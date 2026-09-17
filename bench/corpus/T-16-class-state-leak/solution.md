# T-16-class-state-leak — solution (never shown to a run)

One file: repo/cart/cart.py. `items` is a CLASS attribute — every instance shares one list. Move it into __init__ as an instance attribute.

Red->green: pytest fails (test_carts_are_independent, test_new_cart_starts_empty) before, passes after. Everything except repo/cart/cart.py stays byte-identical.
