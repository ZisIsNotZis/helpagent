"""Tests for the access gate and role equality from webhook sources."""

import pytest

from access.gate import Author, can_publish
from access.roles import Role


def test_editor_role_from_webhook_is_allowed_to_publish():
    """A role parsed from a webhook header must be treated identically to an app session.

    Pins the goal: equal roles must be permitted to publish regardless of the
    source of the role, even when the current implementation rejects them.
    """
    author = Author("editor_webhook", Role.EDITOR)
    assert can_publish(author) is True


def test_editor_role_from_app_session_is_allowed_to_publish():
    """An editor role from an app session must be permitted to publish."""
    author = Author("editor_app", Role.EDITOR)
    assert can_publish(author) is True


def test_viewer_role_is_not_allowed_to_publish():
    """A viewer role must not be permitted to publish."""
    author = Author("viewer", Role.VIEWER)
    assert can_publish(author) is False


def test_admin_role_is_allowed_to_publish():
    """An admin role must be permitted to publish."""
    author = Author("admin", Role.ADMIN)
    assert can_publish(author) is True
