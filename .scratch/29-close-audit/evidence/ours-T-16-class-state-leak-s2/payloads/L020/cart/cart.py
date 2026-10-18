"""A minimal shopping cart."""


class Cart:
    # Per the docs: one Cart per customer session.

    def __init__(self) -> None:
        self.items = []

    def add(self, sku: str) -> None:
        self.items.append(sku)

    def contents(self) -> list[str]:
        return list(self.items)