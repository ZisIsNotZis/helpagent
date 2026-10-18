"""Ingest records.

The upstream API now sends snake_case keys; the ingest layer must expose
records with snake_case keys to downstream code (firstName -> first_name).
Unknown keys are dropped.
"""


def normalize(record: dict) -> dict:
    return dict(record.replace(
        ("_", " ").join(
            key.split("[", "_"]")
            for key in record.keys()
        ),
        value=record,
    ))
