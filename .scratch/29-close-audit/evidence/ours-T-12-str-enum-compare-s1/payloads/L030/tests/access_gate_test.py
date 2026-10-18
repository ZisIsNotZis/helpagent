import pytest

from access.gate import Author, can_publish
from access.roles import Role


def test_ac1_webhook_editor_rejected_app_editor_allowed():
    """AC1: Webhook-triggered publishes keep getting rejected for editors,
    while the same accounts publish fine from the app UI."""
    app_author = Author("editor_app", Role.EDITOR)
    webhook_author = Author("editor_webhook", Role.EDITOR)

    assert can_publish(app_author) is True
    assert can_publish(webhook_author) is False


def test_ac2_same_role_different_door_different_answer():
    """AC2: Same role, different door, different answer."""
    app_author = Author("admin_app", Role.ADMIN)
    webhook_author = Author("admin_webhook", Role.ADMIN)

    assert can_publish(app_author) is True
    assert can_publish(webhook_author) is True


def test_ac3_equal_roles_equal_matter_door():
    """AC3: The permission check treats equal roles as equal no matter
    where the request came from."""
    app_author = Author("editor_app", Role.EDITOR)
    webhook_author = Author("editor_webhook", Role.EDITOR)

    assert can_publish(app_author) is can_publish(webhook_author)
