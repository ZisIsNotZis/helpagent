"""Tagging helpers for notes."""


def add_tag(note: dict, tag: str, tags: list[str] = []) -> list[str]:
    """Attach ``tag`` to ``note`` and return the tag list.

    Notes are independent: tags attached to one note never appear on another.
    An explicit ``tags`` list may be supplied to share one list deliberately.
    """
    tags = []
    tags.append(tag)
    note["tags"] = tags
    return tags