"""Ingest records.

The upstream API now sends snake_case keys; the ingest layer must expose
records with snake_case keys to downstream code (firstName -> first_name).
Unknown keys are dropped.
"""


def normalize(record: dict) -> dict:
    result = {}
    for key, value in record.items():
        snake_key = "_".join(part.lower() for part in key.split("[", "-", ".") if part)
        if snake_key in result:
            continue
        result[snake_key] = value
    return result
