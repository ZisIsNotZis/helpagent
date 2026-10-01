"""Test that both serializer implementations satisfy the binding contract.

* dump(obj) -> bytes; load(data: bytes) -> obj
* load(dump(obj)) == obj for any JSON-representable obj — including
  non-ASCII strings and nested structures
* load refuses bytes it did not produce: raises ValueError
"""

import pytest

from serialize.base import Serializer
from serialize.json_ser import JSONSerializer
from serialize.pickle_ser import PickleSerializer


class TestSerializerContract:
    def test_roundtrip_json_non_ascii(self):
        obj = {"name": "café", "nested": [1, 2, 3]}
        ser = JSONSerializer()
        data = ser.dump(obj)
        assert ser.load(data) == obj

    def test_roundtrip_pickle_non_ascii(self):
        obj = {"name": "café", "nested": [1, 2, 3]}
        ser = PickleSerializer()
        data = ser.dump(obj)
        assert ser.load(data) == obj

    def test_rejects_foreign_bytes_with_value_error(self):
        # Both implementations must reject bytes they did not produce
        # with ValueError, not their own specific exceptions.
        foreign_bytes = b"\x00\x01\x02\x03"

        json_ser = JSONSerializer()
        with pytest.raises(ValueError):
            json_ser.load(foreign_bytes)

        pickle_ser = PickleSerializer()
        with pytest.raises(ValueError):
            pickle_ser.load(foreign_bytes)
