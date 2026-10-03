"""Service layer caller."""

from api.client import fetch


def sync_record(record_id: str) -> str:
    return fetch(f"/records/{record_id}", payload="sync")
