"""JSON implementation."""

import json

from serialize.base import Serializer


class JSONSerializer(Serializer):
    def dump(self, obj) -> bytes:
        return json.dumps(obj, ensure_ascii=False).encode("utf-8")

    def load(self, data: bytes):
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("load refused foreign bytes") from exc
