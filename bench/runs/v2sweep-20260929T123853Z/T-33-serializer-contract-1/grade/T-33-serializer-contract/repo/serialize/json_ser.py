"""JSON implementation."""

import json

from serialize.base import Serializer


class JSONSerializer(Serializer):
    def dump(self, obj) -> bytes:
        return json.dumps(obj).encode()

    def load(self, data: bytes):
        return json.loads(data.decode("ascii"))
