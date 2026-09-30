"""Public API client."""

from api.transport import send


def fetch(url: str, payload: str = "") -> str:
    return send(url, payload)
