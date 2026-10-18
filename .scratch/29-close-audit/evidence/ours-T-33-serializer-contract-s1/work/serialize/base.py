"""Serializer protocol.

CONTRACT (binding for every implementation):
  * dump(obj) -> bytes; load(data: bytes) -> obj
  * load(dump(obj)) == obj for any JSON-representable obj — including
    non-ASCII strings and nested structures
  * load refuses bytes it did not produce: raises ValueError
"""


class Serializer:
    def dump(self, obj) -> bytes:
        raise NotImplementedError

    def load(self, data: bytes):
        raise NotImplementedError
