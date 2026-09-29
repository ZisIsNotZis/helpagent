"""Tests for the tagging helpers."""

from tagger.notes import add_tag


def test_tags_attach_to_their_note():
    note = {"title": "groceries"}
    add_tag(note, "errand")
    assert note["tags"] == ["errand"]


def test_notes_do_not_share_tags():
    first = {"title": "groceries"}
    second = {"title": "workout"}
    add_tag(first, "errand")
    add_tag(second, "gym")
    assert second["tags"] == ["gym"]
