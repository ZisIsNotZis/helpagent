"""snake_case contract tests."""

from ingest.records import normalize


def test_camel_to_snake():
    assert normalize({"firstName": "Ada"}) == {"first_name": "Ada"}


def test_snake_keys_pass_through():
    assert normalize({"user_id": 7}) == {"user_id": 7}


def test_unknown_keys_dropped():
    assert normalize({"firstName": "A", "junkField": 1}) == {"first_name": "A"}
