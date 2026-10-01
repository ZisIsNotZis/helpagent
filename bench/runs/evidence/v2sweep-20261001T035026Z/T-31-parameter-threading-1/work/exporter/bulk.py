"""Bulk exporter - the other fetch caller."""

from api.client import fetch


def export_all(ids: list, timeout: float = 1.0) -> list:
    return [fetch(f"/export/{i}", timeout=timeout) for i in ids]
