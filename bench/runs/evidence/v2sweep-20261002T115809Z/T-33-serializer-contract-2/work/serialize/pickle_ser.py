"""Pickle implementation."""

import pickle
from pickle import UnpicklingError

from serialize.base import Serializer


class PickleSerializer(Serializer):
    def dump(self, obj) -> bytes:
        return pickle.dumps(obj)

    def load(self, data: bytes):
        try:
            return pickle.loads(data)
        except (UnpicklingError, pickle.PickleError) as e:
            raise ValueError("Invalid pickle data") from e
