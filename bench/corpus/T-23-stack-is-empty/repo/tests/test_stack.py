"""The docs promise is_empty() alongside push/pop/peek."""

from stack.stack import Stack


def test_empty_on_construction():
    assert Stack().is_empty() is True


def test_not_empty_after_push():
    s = Stack()
    s.push(1)
    assert s.is_empty() is False


def test_empty_again_after_pop():
    s = Stack()
    s.push(1)
    s.pop()
    assert s.is_empty() is True
