"""Tests for note tagging behavior."""


def test_notes_do_not_share_tags():
    """Tags attached to one note must not appear on another note."""
    note1 = {"id": "note1", "tags": []}
    note2 = {"id": "note2", "tags": []}

    add_tag(note1, "errand")

    assert note1["tags"] == ["errand"]
    assert note2["tags"] == []


def test_tags_attach_to_their_note():
    """Tags attach to the note they are added to."""
    note = {"id": "note1", "tags": []}

    add_tag(note, "errand")

    assert note["tags"] == ["errand"]
    assert len(note["tags"]) == 1
    assert note["tags"][0] == "errand"