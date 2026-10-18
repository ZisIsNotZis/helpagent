"""Role definitions."""


class Role(str):
    """A user role. Compares equal to its plain text wherever it comes from —
    app sessions and parsed webhook headers must behave identically."""

    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"
