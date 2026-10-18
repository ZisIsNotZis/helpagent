"""Test suite for the serializer contract.

Pins the goal: every implementation must roundtrip any JSON-representable
object (including non-ASCII text) and must REJECT bytes it did not produce
with ValueError.
"""

import pytest

from serialize.base import Serializer
from serialize.json_ser import JSONSerializer
from serialize.pickle_ser import PickleSerializer


def test_json_roundtrip_non_ascii():
    """JSON must roundtrip non-ASCII strings and nested structures."""
    obj = {"name": "café", "nested": [1, 2, "中文"]}
    ser = JSONSerializer()
    data = ser.dump(obj)
    assert ser.load(data) == obj


def test_json_rejects_foreign_bytes():
    """JSON must raise ValueError on bytes it did not produce."""
    ser = JSONSerializer()
    with pytest.raises(ValueError):
        ser.load(b"not json data")


def test_pickle_roundtrip():
    """Pickle must roundtrip any JSON-representable object."""
    obj = {"name": "café", "nested": [1, 2, "中文"]}
    ser = PickleSerializer()
    data = ser.dump(obj)
    assert ser.load(data) == obj


def test_pickle_rejects_foreign_bytes():
    """Pickle must raise ValueError on bytes it did not produce."""
    ser = PickleSerializer()
    with pytest.raises(ValueError):
        ser.load(b"foreign bytes")
