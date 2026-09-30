```python
"""Public API client."""

from api.transport import send


def fetch(url: str, payload: str = "", timeout: float = 1.0) -> str:
    return send(url, payload, timeout=timeout)
```