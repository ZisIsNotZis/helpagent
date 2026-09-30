"""The base.py contract, verified for every shipped implementation."""

import pytest

from serialize.json_ser import JSONSerializer
from serialize.pickle_ser import PickleSerializer

IMPLS = [JSONSerializer(), PickleSerializer()]


@pytest.mark.parametrize("ser", IMPLS, ids=lambda s: type(s).__name__)
def test_roundtrip_non_ascii(ser):
    obj = {"name": "Zoë", "tags": ["café", "日本語"]}
    assert ser.load(ser.dump(obj)) == obj


@pytest.mark.parametrize("ser", IMPLS, ids=lambda s: type(s).__name__)
def test_load_refuses_foreign_bytes(ser):
    with pytest.raises(ValueError):
        ser.load(b"not produced by dump")


@pytest.mark.parametrize("ser", IMPLS, ids=lambda s: type(s).__name__)
def test_roundtrip_nested(ser):
    obj = {"a": [1, {"b": None}], "c": True}
    assert ser.load(ser.dump(obj)) == obj
