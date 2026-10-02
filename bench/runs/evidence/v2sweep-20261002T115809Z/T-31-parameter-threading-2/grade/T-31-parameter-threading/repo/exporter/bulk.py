"""Bulk exporter - the other fetch caller."""

from api.client import fetch


def export_all(ids: list) -> list:
    return [fetch(f"/export/{i}") for i in ids]
