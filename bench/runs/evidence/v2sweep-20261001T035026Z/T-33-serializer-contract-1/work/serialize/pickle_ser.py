"""Pickle implementation."""

import pickle

from serialize.base import Serializer


class PickleSerializer(Serializer):
    def dump(self, obj) -> bytes:
        return pickle.dumps(obj)

    def load(self, data: bytes):
        if not isinstance(data, (bytes, bytearray)) or len(data) == 0:
            raise ValueError("Only bytes produced by this serializer are accepted.")
        try:
            return pickle.loads(data)
        except Exception as e:
            if isinstance(e, pickle.UnpicklingError):
                raise ValueError("Only bytes produced by this serializer are accepted.")
            raise