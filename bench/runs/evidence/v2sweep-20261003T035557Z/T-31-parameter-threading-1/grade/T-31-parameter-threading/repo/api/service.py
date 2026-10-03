"""Service layer caller."""

from api.client import fetch
from api.client import sync_record


def sync_record(record_id: str, timeout: float = 1.0) -> str:
    return fetch(f"/records/{record_id}", payload="sync", timeout=timeout)