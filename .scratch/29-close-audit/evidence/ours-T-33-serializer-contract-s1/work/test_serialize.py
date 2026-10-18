import pytest

from serialize.base import Serializer
from serialize.json_ser import JSONSerializer
from serialize.pickle_ser import PickleSerializer




def test_pickle_rejects_foreign_bytes():
    """Pickle must raise ValueError on bytes it did not produce."""
    ser = PickleSerializer()
    with pytest.raises(ValueError):
        ser.load(b"foreign bytes")
