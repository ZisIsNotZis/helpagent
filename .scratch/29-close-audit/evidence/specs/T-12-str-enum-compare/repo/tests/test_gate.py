"""Tests for the access gate."""

from access.gate import Author, can_publish
from access.roles import Role


def test_session_editor_may_publish():
    assert can_publish(Author("ada", Role.EDITOR)) is True


def test_webhook_parsed_editor_may_publish():
    # the webhook path constructs the role from the raw header value
    assert can_publish(Author("bob", Role("editor"))) is True


def test_viewer_cannot_publish():
    assert can_publish(Author("eve", Role.VIEWER)) is False
