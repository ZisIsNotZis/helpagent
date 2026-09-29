"""JSON implementation."""

import json

from serialize.base import Serializer
from serialize.base import JSONSerializer


class JSONSerializer(Serializer):
    def dump(self, obj) -> bytes:
        return json.dumps(obj).encode("utf-8")

    def load(self, data: bytes):
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid JSON bytes") from exc