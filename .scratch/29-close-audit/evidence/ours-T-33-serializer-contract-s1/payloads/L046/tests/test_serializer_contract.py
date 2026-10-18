"""Test suite verifying the serializer layer binding contract."""

import json

import pytest

from serialize.base import Serializer
from serialize.json_ser import JSONSerializer
from serialize.pickle_ser import PickleSerializer


def test_ac1_roundtrip_and_value_error():
    """AC1: Both implementations must roundtrip JSON-representable objects and reject foreign bytes with ValueError."""
    json_ser = JSONSerializer()
    pickle_ser = PickleSerializer()

    # Test roundtrip with non-ASCII text
    obj = "café"
    json_bytes = json_ser.dump(obj)
    assert json_bytes == b'"caf\u00e9"'
    assert json_ser.load(json_bytes) == obj

    pickle_bytes = pickle_ser.dump(obj)
    assert pickle_ser.load(pickle_bytes) == obj

    # Test rejection of foreign bytes with ValueError
    foreign_bytes = b'\xff\xfe\x00\x01'
    with pytest.raises(ValueError):
        json_ser.load(foreign_bytes)
    with pytest.raises(ValueError):
        pickle_ser.load(foreign_bytes)


def test_ac2_violation_behavior():
    """AC2: Verify the shipped implementations correctly violate the contract by raising ValueError."""
    json_ser = JSONSerializer()
    pickle_ser = PickleSerializer()

    # JSON mangles non-ASCII names and raises ValueError on foreign bytes
    obj = "café"
    mangled_bytes = json_ser.dump(obj)
    assert mangled_bytes != b'"café"'

    with pytest.raises(ValueError):
        json_ser.load(b'\xff\xfe')

    # Pickle raises ValueError on foreign bytes instead of its own UnpicklingError
    with pytest.raises(ValueError):
        pickle_ser.load(b'\xff\xfe')


def test_ac3_both_implementations_in_contract():
    """AC3: Both shipped implementations are active and satisfy the base Serializer contract."""
    json_ser = JSONSerializer()
    pickle_ser = PickleSerializer()

    assert isinstance(json_ser, Serializer)
    assert isinstance(pickle_ser, Serializer)

    # Ensure they can serialize and deserialize basic data
    test_data = [1, 2, 3]
    json_bytes = json_ser.dump(test_data)
    assert json_ser.load(json_bytes) == test_data

    pickle_bytes = pickle_ser.dump(test_data)
    assert pickle_ser.load(pickle_bytes) == test_data
