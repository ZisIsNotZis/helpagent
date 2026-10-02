"""Test that both serializers satisfy the binding contract in serialize/base.py."""

import pytest

from serialize.base import Serializer
from serialize.json_ser import JSONSerializer
from serialize.pickle_ser import PickleSerializer


def test_json_roundtrip_non_ascii():
    ser = JSONSerializer()
    obj = {"name": "café", "nested": [1, 2, 3]}
    data = ser.dump(obj)
    assert ser.load(data) == obj


def test_json_rejects_foreign_bytes():
    ser = JSONSerializer()
    with pytest.raises(ValueError):
        ser.load(b"not json at all")


def test_pickle_roundtrip():
    ser = PickleSerializer()
    obj = {"name": "café", "nested": [1, 2, 3]}
    data = ser.dump(obj)
    assert ser.load(data) == obj


def test_pickle_rejects_foreign_bytes():
    ser = PickleSerializer()
    with pytest.raises(ValueError):
        ser.load(b"not pickle data")


def test_base_contract_is_binding():
    assert issubclass(JSONSerializer, Serializer)
    assert issubclass(PickleSerializer, Serializer)
