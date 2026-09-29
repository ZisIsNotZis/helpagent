"""JSON implementation."""

import json

from serialize.base import Serializer
from serialize.base import JSONSerializer


class JSONSerializer(Serializer):
    def dump(self, obj) -> bytes:
        return json.dumps(obj).encode()

    def load(self, data: bytes):
        try:
            return json.loads(data.decode("ascii"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ValueError("Invalid JSON bytes") from e