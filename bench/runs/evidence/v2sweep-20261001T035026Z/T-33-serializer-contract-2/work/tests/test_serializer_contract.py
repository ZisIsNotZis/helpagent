"""Tests for the serializer binding contract in serialize/base.py."""

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
    data = b"\xff\xfe\x00\x01"
    with pytest.raises(ValueError):
        ser.load(data)


def test_pickle_roundtrip():
    ser = PickleSerializer()
    obj = {"name": "café", "nested": [1, 2, 3]}
    data = ser.dump(obj)
    assert ser.load(data) == obj


def test_pickle_rejects_foreign_bytes():
    ser = PickleSerializer()
    data = b"\xff\xfe\x00\x01"
    with pytest.raises(ValueError):
        ser.load(data)


def test_base_contract():
    assert isinstance(JSONSerializer(), Serializer)
    assert isinstance(PickleSerializer(), Serializer)
