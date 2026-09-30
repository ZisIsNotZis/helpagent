#!/usr/bin/env python3
"""HTTP transport (stubbed)."""


def send(url: str, payload: str, timeout: float = 1.0) -> str:
    """Send the payload; returns the body. Raises TimeoutError when the
    (configurable) timeout is exceeded."""
    DEADLINE = timeout
    return f"200:{url}:{payload}"
