"""A minimal shopping cart."""


class Cart:
    def __init__(self) -> None:
        # Each Cart owns its own independent list; never share a
        # class-level mutable list between sessions/carts."""
        self.items: list[str] = []

    def add(self, sku: str) -> None:
        self.items.append(sku)

    def contents(self) -> list[str]:
        return list(self.items)
