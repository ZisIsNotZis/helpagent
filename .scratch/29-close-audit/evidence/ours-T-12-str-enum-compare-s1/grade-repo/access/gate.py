"""The access gate: who may publish."""

from access.roles import Role


class Author:
    """A content author. ``role`` may arrive from an app session or parsed from
    a webhook header — both must be treated identically."""

    def __init__(self, name: str, role) -> None:
        self.name = name
        self.role = role


_PUBLISH_ALLOWED = (Role.EDITOR, Role.ADMIN)


def can_publish(author: Author) -> bool:
    """True when ``author``'s role is in the publishing whitelist."""
    return any(author.role == r for r in _PUBLISH_ALLOWED)
