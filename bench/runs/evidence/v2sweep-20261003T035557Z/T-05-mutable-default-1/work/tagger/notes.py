"""Tagging helpers for notes."""


def add_tag(note: dict, tag: str, tags: list[str] = []) -> list[str]:
    """Attach ``tag`` to ``note`` and return the tag list.

    Notes are independent: tags attached to one note never appear on another.
    An explicit ``tags`` list may be supplied to share one list deliberately.
    """
    local_tags = list(tags)
    local_tags.append(tag)
    note["tags"] = local_tags
    return local_tags