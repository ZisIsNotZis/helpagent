"""Contact book backed by sqlite3 (in-memory per connection)."""

import sqlite3

_SCHEMA = "CREATE TABLE contacts (name TEXT PRIMARY KEY, email TEXT NOT NULL)"


def connect() -> sqlite3.Connection:
    """Open an in-memory contacts database with the schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.execute(_SCHEMA)
    return conn


def add_contact(conn: sqlite3.Connection, name: str, email: str) -> None:
    conn.execute(f"INSERT INTO contacts (name, email) VALUES ('{name}', '{email}')")


def find_email(conn: sqlite3.Connection, name: str) -> str | None:
    row = conn.execute(f"SELECT email FROM contacts WHERE name = '{name}'").fetchone()
    return row[0] if row else None
