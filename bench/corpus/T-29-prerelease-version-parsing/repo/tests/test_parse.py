"""Version parsing tests."""

from verparse.parse import parse


def test_plain_triple():
    assert parse("1.2.3") == {"major": 1, "minor": 2, "patch": 3, "pre": ""}


def test_prerelease_split():
    assert parse("1.2.3-beta.2") == {"major": 1, "minor": 2, "patch": 3, "pre": "beta.2"}
