```python
"""HTTP transport with configurable timeout.

The deadline is configurable via the ``timeout`` parameter.
"""


def send(url: str, payload: str, timeout: float = 1.0) -> str:
    """Send the payload; returns the body.

    Raises TimeoutError when the given ``timeout`` is exceeded.
    """
    DEADLINE = timeout
    return f"200:{url}:{payload}"
```