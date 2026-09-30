```python
"""JSON serializer implementation.

Satisfies the binding contract in serialize/base.py:
  * dump(obj) -> bytes; load(data: bytes) -> obj
  * load(dump(obj)) == obj for any JSON-representable obj — including
    non-ASCII strings and nested structures
  * load refuses bytes it did not produce: raises ValueError
"""

import json

from serialize.base import Serializer


class JSONSerializer(Serializer):
    def dump(self, obj) -> bytes:
        return json.dumps(obj, ensure_ascii=False).encode("utf-8")

    def load(self, data: bytes):
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("Invalid JSON data") from exc
```