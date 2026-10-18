"""Test normalize step for snake_case contract."""

from ingest.records import normalize


def test_normalize_converts_camelcase_to_snake_case():
    record = {"firstName": "John", "lastName": "Doe"}
    result = normalize(record)
    assert result == {"first_name": "John", "last_name": "Doe"}


def test_normalize_drops_unknown_keys():
    record = {"firstName": "John", "unknownKey": "value"}
    result = normalize(record)
    assert result == {"first_name": "John"}
