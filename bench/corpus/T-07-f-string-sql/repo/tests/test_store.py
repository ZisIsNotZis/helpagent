"""Tests for the contact store."""

from contacts.store import add_contact, connect, find_email


def test_add_and_find_plain_name():
    conn = connect()
    add_contact(conn, "Alice", "alice@example.com")
    assert find_email(conn, "Alice") == "alice@example.com"


def test_name_with_apostrophe_round_trips():
    conn = connect()
    add_contact(conn, "Tim O'Brien", "tim@example.com")
    assert find_email(conn, "Tim O'Brien") == "tim@example.com"
