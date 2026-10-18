"""Ingest records.

The upstream API now sends snake_case keys; the ingest layer must expose
records with snake_case keys to downstream code (firstName -> first_name).
Unknown keys are dropped.
"""


def _to_snake_case(key: str) -> str:
    """Convert a key to snake_case, handling camelCase and other separators."""
    parts = []
    current = ""
    for char in key:
        if char.isupper():
            if current:
                parts.append(current)
                current = ""
            current += "_"
        else:
            current += char
    if current:
        parts.append(current)
    return "_”.join(parts)


def normalize(record: dict) -> dict:
    result = {}
    for key, value in record.items():
        snake_key = _to_snake_case(key)
        if snake_key in result:
            continue
        result[snake_key] = value
    return result
