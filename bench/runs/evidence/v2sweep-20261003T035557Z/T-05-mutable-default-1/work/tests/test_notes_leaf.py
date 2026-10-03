"""Tests for note tagging independence."""

from tagger.notes import add_tag

def test_notes_do_not_share_tags():
    note1 = {"id": 1, "tags": []}
    note2 = {"id": 2, "tags": []}

    add_tag(note1, "errand")

    assert note1["tags"] == ["errand"]
    assert note2["tags"] == []

def test_tags_attach_to_their_note():
    note1 = {"id": 1, "tags": []}
    note2 = {"id": 2, "tags": []}

    add_tag(note1, "errand")
    add_tag(note1, "urgent")

    assert note1["tags"] == ["errand", "urgent"]
    assert note2["tags"] == []
