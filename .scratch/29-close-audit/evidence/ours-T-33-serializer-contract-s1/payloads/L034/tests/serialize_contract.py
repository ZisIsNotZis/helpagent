import pytest

from serialize.base import Serializer
from serialize.json_ser import JSONSerializer
from serialize.pickle_ser import PickleSerializer


def test_ac1_roundtrip_and_value_error():
    """AC1: Both implementations must roundtrip JSON-representable objects
    including non-ASCII text and reject foreign bytes with ValueError."""
    json_ser = JSONSerializer()
    pickle_ser = PickleSerializer()

    # Roundtrip non-ASCII text
    obj = "café"
    json_bytes = json_ser.dump(obj)
    assert json_ser.load(json_bytes) == obj
    pickle_bytes = pickle_ser.dump(obj)
    assert pickle_ser.load(pickle_bytes) == obj

    # Reject foreign bytes with ValueError
    with pytest.raises(ValueError):
        json_ser.load(b"\xff\xfe\x00\x01")
    with pytest.raises(ValueError):
        pickle_ser.load(b"\xff\xfe\x00\x01")


def test_ac2_violation_fix():
    """AC2: Verify shipped implementations fix mangled non-ASCII, wrong
    errors, and UnpicklingError conversion to ValueError."""
    json_ser = JSONSerializer()
    pickle_ser = PickleSerializer()

    # JSON must preserve non-ASCII names without mangling
    name = "café"
    dumped = json_ser.dump(name)
    assert name in dumped.decode("utf-8")

    # JSON must raise ValueError on foreign bytes
    with pytest.raises(ValueError):
        json_ser.load(b"\xff\xfe")

    # Pickle must raise ValueError on foreign bytes (not UnpicklingError)
    with pytest.raises(ValueError):
        pickle_ser.load(b"\xff\xfe")


def test_ac3_both_implementations():
    """AC3: Ensure both shipped implementations are bound to the contract."""
    assert isinstance(JSONSerializer(), Serializer)
    assert isinstance(PickleSerializer(), Serializer)
