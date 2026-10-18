"""Pickle implementation."""

import pickle

from serialize.base import Serializer


class PickleSerializer(Serializer):
    def dump(self, obj) -> bytes:
        return pickle.dumps(obj)

    def load(self, data: bytes):
        try:
            return pickle.loads(data)
        except pickle.UnpicklingError as e:
            raise ValueError("Invalid pickled data") from e
        except Exception as e:
            raise ValueError("Invalid pickled data") from e
