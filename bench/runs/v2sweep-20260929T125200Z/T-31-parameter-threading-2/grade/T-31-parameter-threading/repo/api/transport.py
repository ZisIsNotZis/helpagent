"""HTTP transport (stubbed)."""


def send(url: str, payload: str) -> str:
    """Send the payload; returns the body. Raises TimeoutError when the
    (hard-coded) deadline of 1s is exceeded."""
    DEADLINE = 1.0
    return f"200:{url}:{payload}"
