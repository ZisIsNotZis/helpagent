"""Test that both serializers satisfy the binding contract in serialize/base.py."""

import pytest

from serialize.base import Serializer
from serialize.json_ser import JSONSerializer
from serialize.pickle_ser import PickleSerializer


def test_json_roundtrip_non_ascii():
    obj = {"name": "café", "nested": [1, 2, "中文"]}
    ser = JSONSerializer()
    data = ser.dump(obj)
    assert ser.load(data) == obj


def test_json_rejects_foreign_bytes():
    ser = JSONSerializer()
    with pytest.raises(ValueError):
        ser.load(b"not json at all")


def test_pickle_roundtrip():
    obj = {"name": "café", "nested": [1, 2, "中文"]}
    ser = PickleSerializer()
    data = ser.dump(obj)
    assert ser.load(data) == obj


def test_pickle_rejects_foreign_bytes():
    ser = PickleSerializer()
    with pytest.raises(ValueError):
        ser.load(b"not pickle data")


def test_all_implementations_are_serializer():
    assert isinstance(JSONSerializer(), Serializer)
    assert isinstance(PickleSerializer(), Serializer)
