"""Tagging helpers for notes."""


def add_tag(note: dict, tag: str, tags: list[str] = []) -> list[str]:
    """Attach ``tag`` to ``note`` and return the tag list.

    Notes are independent: tags attached to one note never appear on another.
    An explicit ``tags`` list may be supplied to share one list deliberately.
    """
    if not isinstance(note, dict) or "tags" not in note:
        raise ValueError("note must be a dict with a 'tags' key")
    if not isinstance(tags, list):
        raise TypeError("tags must be a list")
    if tag not in tags:
        tags = list(tags)
        tags.append(tag)
    note["tags"] = tags
    return tags
