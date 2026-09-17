"""Slug tests (kebab-case per site conventions)."""

from textkit.slug import slugify


def test_basic_slug():
    assert slugify("Hello World") == "hello-world"


def test_multiple_spaces_collapse():
    assert slugify("  a   b  ") == "a-b"
