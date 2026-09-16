"""Domain errors for the order service."""


class OrderError(Exception):
    """Base class for every order-domain failure."""


class OrderValidationError(OrderError):
    """An order violates a validation rule (size, contents, ...)."""
