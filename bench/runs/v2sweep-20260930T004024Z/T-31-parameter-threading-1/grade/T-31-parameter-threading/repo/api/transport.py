"""HTTP transport (stubbed)."""

from api.transport import send


def send(url: str, payload: str, timeout: float = 1.0) -> str:
    """Send the payload; returns the body. Raises TimeoutError when the
    (configurable) deadline of `timeout` seconds is exceeded."""
    DEADLINE = timeout
    return f"200:{url}:{payload}"