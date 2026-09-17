"""Corruption must not vanish."""

import json

import pytest

from storage.errors import StorageError
from storage.store import load


def test_valid_file_loads(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"a": 1}))
    assert load(p) == {"a": 1}


def test_corrupt_file_raises_storage_error(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{not json")
    with pytest.raises(StorageError):
        load(p)
