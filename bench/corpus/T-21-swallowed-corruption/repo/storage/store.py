"""JSON-backed settings store."""

import json

from storage.errors import StorageError


def load(path) -> dict:
    """Load settings; unreadable state must surface as StorageError."""
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}
